import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Salty Quant Terminal",
  description: "Crypto research, validation and paper-trading workspace."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
