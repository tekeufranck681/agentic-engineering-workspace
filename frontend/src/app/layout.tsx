import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
const geist = localFont({
  src: "./fonts/Geist-Variable.woff2",
  variable: "--font-geist-sans",
  display: "swap",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMono-Variable.woff2",
  variable: "--font-geist-mono",
  display: "swap",
  weight: "100 900",
});
export const metadata: Metadata = {
  title: {
    default: "Engineering workspace",
    template: "%s | Engineering workspace",
  },
  description: "Requirements through evidenced delivery.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geist.variable} ${geistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
