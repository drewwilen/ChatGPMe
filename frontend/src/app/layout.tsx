import type { Metadata } from "next";
import Providers from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "ChatGPMe",
  description: "A personalized writing assistant trained on your own documents",
  icons: {
    icon: "/chatgpme-icon.png",
    shortcut: "/chatgpme-icon.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
