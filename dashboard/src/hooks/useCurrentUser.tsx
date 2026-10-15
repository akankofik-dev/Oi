import {
  createContext,
  useContext,
  useMemo,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type { OiUser } from "../api/modules/auth";

type CurrentUserContextValue = {
  user: OiUser | null;
  setUser: Dispatch<SetStateAction<OiUser | null>>;
};

const CurrentUserContext = createContext<CurrentUserContextValue | null>(null);

export function CurrentUserProvider({
  user,
  setUser,
  children,
}: {
  user: OiUser | null;
  setUser: Dispatch<SetStateAction<OiUser | null>>;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ user, setUser }), [user, setUser]);
  return (
    <CurrentUserContext.Provider value={value}>
      {children}
    </CurrentUserContext.Provider>
  );
}

/**
 * Current authenticated user from AuthGuard's ``/auth/me`` result.
 * ``null`` while loading or when the provider is not mounted.
 */
export function useCurrentUser(): OiUser | null {
  return useContext(CurrentUserContext)?.user ?? null;
}

export function useSetCurrentUser(): Dispatch<
  SetStateAction<OiUser | null>
> {
  const ctx = useContext(CurrentUserContext);
  if (!ctx) {
    return () => undefined;
  }
  return ctx.setUser;
}
