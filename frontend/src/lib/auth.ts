import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      authorization: {
        params: {
          // Drive.readonly so we can read all the user's docs for ingestion.
          scope:
            "openid email profile https://www.googleapis.com/auth/drive.readonly",
          access_type: "offline",
          prompt: "consent",
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      // Persist the Google access token into the JWT on first sign-in.
      if (account) {
        token.accessToken = account.access_token;
      }
      return token;
    },
    async session({ session, token }) {
      // Expose the access token to client components via useSession().
      session.accessToken = token.accessToken as string;
      return session;
    },
  },
};
