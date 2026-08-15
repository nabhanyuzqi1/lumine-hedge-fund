import { motion } from "framer-motion";
import { useEffect, useState } from "react";

/**
 * PhilosophySection — Section 41 of UI/UX Rebuild V2 master prompt.
 * 
 * Cinematic editorial typography with sequential reveals and pauses.
 * 
 * NO cards. NO dashboard. NO gradients. NO decorations.
 * Just large typography, subtle motion, and negative space.
 * 
 * Sequence:
 * > Markets are uncertain.
 * [pause]
 * > Models can be wrong.
 * [pause]
 * > Strategies decay.
 * [pause]
 * > Risk is not optional.
 * [pause]
 * # We engineer systems that adapt to uncertainty.
 */

const PHILOSOPHY_LINES = [
  { text: "Markets are uncertain.", delay: 0.4 },
  { text: "Models can be wrong.", delay: 1.4 },
  { text: "Strategies decay.", delay: 2.4 },
  { text: "Risk is not optional.", delay: 3.4 },
];

export function PhilosophySection() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setIsVisible(true);
        }
      },
      { threshold: 0.3 }
    );

    const element = document.getElementById("philosophy");
    if (element) observer.observe(element);

    return () => observer.disconnect();
  }, []);

  return (
    <div
      id="philosophy"
      className="mx-auto flex min-h-[80vh] max-w-5xl flex-col items-center justify-center space-y-16 px-6 py-20"
    >
      {/* Sequential philosophical statements */}
      <div className="w-full space-y-12">
        {PHILOSOPHY_LINES.map((line, index) => (
          <motion.blockquote
            key={index}
            className="border-l-4 border-ink-faint pl-8 text-3xl leading-relaxed text-ink-dim md:text-4xl lg:text-5xl"
            initial={{ opacity: 0, x: -30 }}
            animate={isVisible ? { opacity: 1, x: 0 } : {}}
            transition={{
              duration: 0.8,
              delay: line.delay,
              ease: "easeOut",
            }}
          >
            {line.text}
          </motion.blockquote>
        ))}
      </div>

      {/* Final manifesto */}
      <motion.div
        className="w-full space-y-6 pt-12 text-center"
        initial={{ opacity: 0, y: 30 }}
        animate={isVisible ? { opacity: 1, y: 0 } : {}}
        transition={{
          duration: 1,
          delay: 4.6,
          ease: "easeOut",
        }}
      >
        <h2 className="font-display text-4xl font-bold leading-tight text-ink md:text-5xl lg:text-6xl">
          We engineer systems
          <br />
          that adapt to uncertainty.
        </h2>

        <motion.p
          className="mx-auto max-w-2xl text-base leading-relaxed text-ink-dim md:text-lg"
          initial={{ opacity: 0 }}
          animate={isVisible ? { opacity: 1 } : {}}
          transition={{
            duration: 0.8,
            delay: 5.2,
          }}
        >
          Lumine is built on the assumption that markets will surprise us.
          Our intelligence layer proposes. Our risk engine decides.
          Our validation framework ensures we only deploy what we understand.
        </motion.p>
      </motion.div>
    </div>
  );
}
