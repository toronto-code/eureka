"use client";

import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter, usePathname } from "next/navigation";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "./supabase";

interface AuthState {
  user: User | null;
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error?: string }>;
  signUp: (email: string, password: string, displayName?: string) => Promise<{ error?: string }>;
  signOut: () => Promise<void>;
}

const AuthCtx = createContext<AuthState | null>(null);

const PUBLIC_PATHS = ["/login"];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session ?? null);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  // Redirect-on-auth-change
  useEffect(() => {
    if (loading) return;
    const isPublic = pathname && PUBLIC_PATHS.includes(pathname);
    if (!session && !isPublic) {
      router.replace("/login");
    } else if (session && isPublic) {
      router.replace("/");
    }
  }, [session, loading, pathname, router]);

  const value: AuthState = {
    user: session?.user ?? null,
    session,
    loading,
    async signIn(email, password) {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      return error ? { error: error.message } : {};
    },
    async signUp(email, password, displayName) {
      const { error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: displayName ? { display_name: displayName } : undefined },
      });
      return error ? { error: error.message } : {};
    },
    async signOut() {
      // Wipe DASHBOARD-only data on logout (agent_actions + observer_events).
      // Chats and conversations are kept across sessions — like ChatGPT.
      try {
        const { data: { session: s } } = await supabase.auth.getSession();
        if (s) {
          await Promise.all([
            supabase.from("agent_actions").delete().eq("user_id", s.user.id),
            supabase.from("observer_events").delete().eq("user_id", s.user.id),
          ]);
        }
      } catch {
        // best-effort — sign out anyway
      }
      await supabase.auth.signOut();
    },
  };

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Authenticated fetch — adds the Bearer JWT for the current Supabase session. */
export async function authFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const headers: Record<string, string> = {
    "content-type": "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { ...init, headers });
}
