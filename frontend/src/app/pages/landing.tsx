import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

export function LandingPage() {
  const navigate = useNavigate();

  useEffect(() => {
    navigate("/terminal");
  }, [navigate]);

  return null;
}
