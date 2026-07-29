import { useState } from "react";

export function useAuth() {
  const [user, setUser] = useState(
    localStorage.getItem("token")
  );

  const login = (token: string) => {
    localStorage.setItem("token", token);
    setUser(token);
  };

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
  };

  return {
    isAuthenticated: !!user,
    user,
    login,
    logout,
  };
}