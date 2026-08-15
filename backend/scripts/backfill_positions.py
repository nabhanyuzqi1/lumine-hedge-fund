#!/usr/bin/env python3
"""Backfill positions from fills table.

Creates positions from accumulated fills per (symbol, book, strategy_id).
Calculates weighted average entry price and total position size.

Usage:
    PYTHONPATH=src python scripts/backfill_positions.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, func
from lumine.data.models import Position, Fill
from lumine.data.session import get_sessionmaker


async def backfill_positions() -> dict[str, int]:
    """Create positions from fills that don't have corresponding positions.
    
    Returns:
        Dict with 'created' and 'skipped' counts.
    """
    async with get_sessionmaker()() as session:
        # Group fills by (symbol, book, strategy_id) and calculate aggregates
        result = await session.execute(
            select(
                Fill.symbol,
                Fill.book,
                Fill.strategy_id,
                Fill.side,
                func.sum(Fill.size).label("total_size"),
                func.min(Fill.ts).label("opened_at"),
                func.min(Fill.lineage_id).label("first_lineage_id"),
            )
            .where(Fill.side == "BUY")  # Only long positions for now
            .group_by(Fill.symbol, Fill.book, Fill.strategy_id, Fill.side)
        )
        
        groups = result.all()
        created = 0
        skipped = 0
        
        for group in groups:
            symbol, book, strategy_id, side, total_size, opened_at, first_lineage_id = group
            
            # Check if position already exists
            existing = await session.execute(
                select(Position).where(
                    Position.symbol == symbol,
                    Position.book == book,
                    Position.strategy_id == strategy_id,
                    Position.status == "open",
                )
            )
            existing_pos = existing.scalar_one_or_none()
            
            if existing_pos:
                print(f"⚠️  Position already exists for {symbol}/{book}/{strategy_id}")
                skipped += 1
                continue
            
            # Get all fills for this group to calculate weighted average
            fills_result = await session.execute(
                select(Fill).where(
                    Fill.symbol == symbol,
                    Fill.book == book,
                    Fill.strategy_id == strategy_id,
                    Fill.side == side,
                ).order_by(Fill.ts)
            )
            fills = fills_result.scalars().all()
            
            if not fills:
                continue
            
            # Calculate weighted average entry price
            total_value = sum(f.size * f.price for f in fills)
            avg_entry = (total_value / total_size).quantize(Decimal("0.00001"))
            
            # Create position
            position = Position(
                symbol=symbol,
                book=book,
                strategy_id=strategy_id,
                side=side.lower(),
                size=total_size,
                avg_entry=avg_entry,
                opened_at=opened_at,
                opened_lineage=first_lineage_id,
                status="open",
            )
            
            session.add(position)
            created += 1
            
            print(f"✅ Created position: {symbol} {side} {total_size} @ {avg_entry}")
            print(f"   book={book}, strategy={strategy_id}")
            print(f"   from {len(fills)} fills, opened_at={opened_at}")
        
        if created > 0:
            await session.commit()
            print(f"\n✅ Committed {created} positions")
        else:
            print(f"\n⚠️  No positions created")
        
        return {"created": created, "skipped": skipped}


async def main() -> None:
    """Run backfill."""
    print("=" * 60)
    print("Positions Backfill from Fills")
    print("=" * 60)
    print()
    
    stats = await backfill_positions()
    
    print()
    print("=" * 60)
    print(f"Summary: {stats['created']} created, {stats['skipped']} skipped")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
