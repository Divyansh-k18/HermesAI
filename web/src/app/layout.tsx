import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import "./globals.css";
import { Providers } from "@/components/providers";

// Fonts are bundled with the app (the `geist` package), so nothing is downloaded at build or dev time.

export const metadata: Metadata = {
  title: { default: "Hermes AI", template: "%s · Hermes AI" },
  description: "Intelligence in Motion. Agentic workflow automation with human accountability.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
