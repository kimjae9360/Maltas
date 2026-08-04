"use client";

import { useEffect } from "react";
import { api } from "@/lib/api";

export function ServerPinger() {
  useEffect(() => {
    // 앱 진입 시 백그라운드로 핑을 날려 Render 서버를 깨운다.
    api.ping();
  }, []);

  return null;
}
