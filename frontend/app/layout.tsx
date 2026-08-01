import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { Providers } from "@/components/providers/query-provider";
import { ThemeProvider } from "@/components/providers/theme-provider";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: {
    default: "GitPilot — Enterprise GitHub Access",
    template: "%s · GitPilot",
  },
  description:
    "Secure, enterprise-grade authentication and GitHub access management for your organization.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <Providers>{children}</Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
