import * as React from "react";
import { TooltipContent, TooltipTrigger } from "@radix-ui/react-tooltip";

const CustomTooltipContent = React.forwardRef<
  React.ElementRef<typeof TooltipContent>,
  React.ComponentPropsWithoutRef<typeof TooltipContent>
>(({ className, sideOffset = 8, ...props }, ref) => (
  <TooltipContent
    ref={ref}
    sideOffset={sideOffset}
    className={[
      "z-50 overflow-hidden rounded-lg bg-overlay border border-line-soft px-3 py-2 text-xs text-ink shadow-panel data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",
      className,
    ].join(" ")}
    {...props}
  />
));
CustomTooltipContent.displayName = "TooltipContent";

export { Tooltip, TooltipProvider } from "@radix-ui/react-tooltip";
export { TooltipTrigger, CustomTooltipContent as TooltipContent };
