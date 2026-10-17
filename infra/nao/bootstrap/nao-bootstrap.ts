/**
 * Task 3N — narrow, trusted, no-network bootstrap for one dataset user's nao account.
 *
 * WHY THIS EXISTS
 * ---------------
 * The brief forbids outgoing email/SMTP, yet nao's ordinary admin "add member" mutation
 * (`team-member.ts` / `organization.routes.ts`) always *sends* a welcome email and flags the
 * account with `requiresPasswordReset = true`. We therefore use the genuine lower-level flow
 * that the upstream seed script (`apps/backend/scripts/db.seed.ts`) already relies on:
 *
 *   createUser(user, account)  ->  org membership  ->  project membership
 *
 * with three deliberate differences from the invited-member flow:
 *
 *   * `requiresPasswordReset` is left FALSE — the credential is a strong random secret that we
 *     provision on purpose for a service account, so there is nothing to force a human to reset;
 *   * no email is ever built or sent (this script has no reference to the email service);
 *   * the password comes from the environment and is NEVER printed to stdout/stderr.
 *
 * The account is created IDEMPOTENTLY and is restart-safe: an existing user keeps its password
 * and data, and an existing credential mapping is preserved. Re-running never rotates secrets.
 *
 * The resulting `app_user_id -> nao account` mapping is written to `--out` (a git-ignored
 * runtime path shared with the Copilot backend's NaoCredentialStore); the mapping is the ONLY
 * place the nao password is materialised.
 *
 * RUN (inside the pinned nao image, cwd /app):
 *   NAO_SERVICE_PASSWORD=... bun run apps/backend/scripts/nao-bootstrap.ts \
 *     --app-user-id <app uuid> --email svc+<app uuid>@nao.invalid \
 *     --name "Asset Copilot (svc)" --project-name asset-knowledge \
 *     --out /bootstrap/nao-credentials.json
 */
import { hashPassword } from 'better-auth/crypto';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

import s from '../src/db/abstractSchema';
import { db } from '../src/db/db';
import { env } from '../src/env';
import * as organizationQueries from '../src/queries/organization.queries';
import * as projectQueries from '../src/queries/project.queries';

interface Args {
	appUserId: string;
	email: string;
	name: string;
	projectName: string;
	out: string;
}

function parseArgs(argv: string[]): Args {
	const map = new Map<string, string>();
	for (let i = 0; i < argv.length; i += 1) {
		const token = argv[i];
		if (!token.startsWith('--')) continue;
		const key = token.slice(2);
		const value = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : '';
		map.set(key, value);
	}
	const appUserId = map.get('app-user-id') ?? process.env.NAO_APP_USER_ID ?? '';
	const projectName = map.get('project-name') ?? 'asset-knowledge';
	// Reserved TLD (.invalid, RFC 2606) — must never be a routable address, so no mail can leave.
	const email = (map.get('email') ?? `svc+${appUserId}@nao.invalid`).toLowerCase();
	const name = map.get('name') ?? 'Asset Copilot Service Account';
	const out = map.get('out') ?? process.env.NAO_CREDENTIALS_OUT ?? '';
	if (!appUserId) throw new Error('missing --app-user-id (or NAO_APP_USER_ID)');
	if (!out) throw new Error('missing --out (or NAO_CREDENTIALS_OUT)');
	return { appUserId, email, name, projectName, out };
}

function fail(message: string): never {
	// Never echo secrets: only fixed, descriptive text reaches stderr.
	console.error(`nao-bootstrap: ${message}`);
	process.exit(1);
}

interface CredentialRecord {
	app_user_id: string;
	nao_user_id: string;
	nao_email: string;
	nao_password: string;
	nao_project_id: string;
}

function writeMapping(out: string, record: CredentialRecord, password: string, created: boolean): void {
	const abs = path.resolve(out);
	let store: Record<string, CredentialRecord> = {};
	if (fs.existsSync(abs)) {
		try {
			store = JSON.parse(fs.readFileSync(abs, 'utf-8')) as Record<string, CredentialRecord>;
		} catch {
			store = {};
		}
	}
	const existing = store[record.app_user_id];
	// Restart-safe: never rotate an existing mapping's password.
	store[record.app_user_id] = {
		...record,
		nao_password: existing?.nao_password ?? password,
	};
	fs.mkdirSync(path.dirname(abs), { recursive: true });
	const tmp = `${abs}.tmp`;
	fs.writeFileSync(tmp, `${JSON.stringify(store, null, 2)}\n`, { mode: 0o600 });
	fs.renameSync(tmp, abs);
	console.log(`nao-bootstrap: mapping written to ${abs}`);
	console.log(`nao-bootstrap: app_user_id=${record.app_user_id}`);
	console.log(`nao-bootstrap: nao_user_id=${record.nao_user_id}`);
	console.log(`nao-bootstrap: nao_project_id=${record.nao_project_id}`);
	console.log(`nao-bootstrap: account ${created ? 'created' : 'already existed (unchanged)'}`);
}

async function main(): Promise<void> {
	const args = parseArgs(process.argv.slice(2));
	const password = process.env.NAO_SERVICE_PASSWORD ?? '';
	if (!password) fail('NAO_SERVICE_PASSWORD is required and must not be empty');

	const projectPath = env.NAO_DEFAULT_PROJECT_PATH;
	if (!projectPath) fail('NAO_DEFAULT_PROJECT_PATH must point at the mounted nao project context');

	const existingUser = await db.query.user.findFirst({
		where: (u, { eq: eqFn }) => eqFn(u.email, args.email),
	});

	let userId: string;
	let created = false;

	if (existingUser) {
		userId = existingUser.id;
	} else {
		userId = crypto.randomUUID();
		const accountId = crypto.randomUUID();
		const hashedPassword = await hashPassword(password);
		await db.transaction(async (tx) => {
			await tx
				.insert(s.user)
				.values({
					id: userId,
					name: args.name,
					email: args.email,
					emailVerified: true,
					// Intentionally provisioned service credential: no forced reset, no email.
					requiresPasswordReset: false,
				})
				.execute();
			await tx
				.insert(s.account)
				.values({ id: accountId, accountId: userId, providerId: 'credential', userId, password: hashedPassword })
				.execute();
		});
		created = true;
	}

	// Shared default organization + the asset-knowledge project; both idempotent.
	const org = await organizationQueries.getOrCreateDefaultOrganization();
	await organizationQueries.addOrgMemberIfMissing({ orgId: org.id, userId, role: 'admin' });

	let project = await projectQueries.getProjectByOrgAndName(org.id, args.projectName);
	if (!project) {
		project = await projectQueries.createProject({
			name: args.projectName,
			type: 'local',
			path: projectPath,
			orgId: org.id,
		});
	}

	const member = await db.query.projectMember.findFirst({
		where: (m, { and: andFn, eq: eqFn }) => andFn(eqFn(m.projectId, project!.id), eqFn(m.userId, userId)),
	});
	if (!member) {
		await projectQueries.addProjectMember({ projectId: project.id, userId, role: 'admin' });
	}

	writeMapping(args.out, {
		app_user_id: args.appUserId,
		nao_user_id: userId,
		nao_email: args.email,
		nao_password: '', // replaced by writeMapping's preserved/supplied value
		nao_project_id: project.id,
	}, password, created);
}

main()
	.then(() => process.exit(0))
	.catch((err) => {
		// Print only the message; never an object that could carry a password field.
		console.error(`nao-bootstrap: ${err instanceof Error ? err.message : 'unexpected failure'}`);
		process.exit(1);
	});
