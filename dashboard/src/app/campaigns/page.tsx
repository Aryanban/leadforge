"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Campaigns merged into Sequences — one concept, one page, like Apollo.
 * This route stays alive only so old bookmarks and links keep working.
 */
export default function CampaignsRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/sequences");
  }, [router]);
  return null;
}
