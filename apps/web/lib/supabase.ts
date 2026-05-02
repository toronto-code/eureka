"use client";

import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const publishable = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY || "";

if (typeof window !== "undefined" && (!url || !publishable)) {
  console.warn(
    "Supabase env vars missing — set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
  );
}

export const supabase = createClient(url || "https://invalid", publishable || "invalid", {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
});
