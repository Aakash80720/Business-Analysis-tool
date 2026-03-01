import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Business Analysis Tool",
  description: "Embedding + Contextual Graph Knowledge Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen flex flex-col">{children}</body>
    </html>
  );
}
