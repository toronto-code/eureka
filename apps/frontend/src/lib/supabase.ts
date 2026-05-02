import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string;
const publishable = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string;

if (!url || !publishable) {
  console.warn("Supabase env vars missing — login/signup will fail until VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY are set");
}

export const supabase = createClient(url || "https://invalid", publishable || "invalid", {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
  },
});
