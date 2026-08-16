import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Utility for merging classes
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface SkeletonProps {
  className?: string;
}

/**
 * Base Skeleton component dengan shimmer animation
 * - Menggunakan CSS animation untuk effect shimmer
 * - Responsive terhadap theme (dark/light)
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md bg-line/50",
        "bg-gradient-to-r from-line/20 via-line/50 to-line/20",
        "bg-[length:200%_100%] animate-shimmer",
        className
      )}
    />
  );
}

/**
 * Skeleton untuk Card component
 */
export function CardSkeleton() {
  return (
    <div className="rounded-panel border border-line bg-raised p-4 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}

/**
 * Skeleton untuk Input field
 */
export function InputSkeleton() {
  return (
    <div className="space-y-1.5">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}

/**
 * Skeleton untuk Button
 */
export function ButtonSkeleton() {
  return <Skeleton className="h-9 w-24 rounded-chip" />;
}

/**
 * Skeleton untuk Table rows
 */
export function TableRowSkeleton({ columns = 4 }: { columns?: number }) {
  return (
    <div className="flex items-center gap-4 py-3">
      {Array.from({ length: columns }).map((_, i) => (
        <Skeleton key={i} className="h-4 flex-1" />
      ))}
    </div>
  );
}

/**
 * Skeleton untuk Hero section
 */
export function HeroSkeleton() {
  return (
    <div className="space-y-6 py-12">
      <Skeleton className="h-3 w-32" />
      <Skeleton className="h-16 w-3/4" />
      <Skeleton className="h-6 w-1/2" />
      <div className="flex gap-3 pt-4">
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-10 w-32" />
      </div>
    </div>
  );
}

/**
 * Skeleton untuk Chart/Graph area
 */
export function ChartSkeleton() {
  return (
    <div className="rounded-panel border border-line bg-raised p-4 space-y-4">
      <div className="flex justify-between">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-16" />
      </div>
      <Skeleton className="h-64 w-full" />
      <div className="flex justify-between">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-3 w-12" />
        ))}
      </div>
    </div>
  );
}

/**
 * Skeleton untuk Loading screen
 */
export function LoadingScreenSkeleton() {
  return (
    <div className="min-h-screen bg-abyss flex items-center justify-center">
      <div className="w-full max-w-md space-y-4">
        <div className="flex items-center justify-center gap-3 mb-8">
          <Skeleton className="h-8 w-8 rounded" />
          <Skeleton className="h-6 w-24" />
        </div>
        <InputSkeleton />
        <InputSkeleton />
        <ButtonSkeleton />
      </div>
    </div>
  );
}