import { Workspace } from "@/components/Workspace";

/**
 * The workspace is a client component; the page itself stays a server component
 * so no backend secret can leak into the browser bundle through this file.
 */
export default function Page() {
  return <Workspace />;
}
