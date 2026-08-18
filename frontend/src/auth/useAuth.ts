import { useContext } from "react";

import type { AuthState } from "./context";
import { AuthContext } from "./context";

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
