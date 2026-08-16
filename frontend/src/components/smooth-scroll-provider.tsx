import { useEffect } from "react";
import Lenis from "lenis";

/**
 * SmoothScrollProvider - Implementasi smooth scrolling dengan Lenis
 * - Butter-smooth scrolling experience
 * - Natural momentum dan easing
 * - Auto cleanup on unmount
 */
export function SmoothScrollProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Initialize Lenis smooth scroll
    const lenis = new Lenis({
      duration: 1.2,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)), // easeOutExpo
      orientation: "vertical",
      gestureOrientation: "vertical",
      smoothWheel: true,
      wheelMultiplier: 1,
      smoothTouch: false, // Disable on touch devices untuk native feel
      touchMultiplier: 2,
      infinite: false,
    });

    // Sync with request animation frame
    function raf(time: number) {
      lenis.raf(time);
      requestAnimationFrame(raf);
    }

    requestAnimationFrame(raf);

    // Cleanup on unmount
    return () => {
      lenis.destroy();
    };
  }, []);

  return <>{children}</>;
}
