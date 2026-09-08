import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "../context/AppContext";
import { AppShell } from "../components/AppShell";

export const metadata: Metadata = {
  title: "Admissions Intelligence",
  description: "AI-powered organization analytics dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AppProvider>
          <AppShell>{children}</AppShell>
        </AppProvider>
      </body>
    </html>
  );
}
