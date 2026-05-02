"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";

/** Same-route query changes (?run=A → ?run=B) must refresh server components. */
export function OrchestrationRunLink({
  runId,
  className,
  style,
  children,
}: {
  runId: string;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  const router = useRouter();
  const href = `/orchestration?run=${runId}`;

  return (
    <Link
      href={href}
      className={className}
      style={style}
      prefetch={false}
      onClick={(e) => {
        const path = window.location.pathname;
        if (path !== "/orchestration") return;
        e.preventDefault();
        router.push(href);
        router.refresh();
      }}
    >
      {children}
    </Link>
  );
}
