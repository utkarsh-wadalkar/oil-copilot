import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./observability";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fieldnote / Asset Intelligence",
  description: "Ask grounded, evidence-linked questions about drone-inspected oil and gas wells.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){var t=localStorage.getItem("fieldnote-theme");if(t!=="light"&&t!=="dark"){t="dark";}document.documentElement.setAttribute("data-theme",t);})();`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
