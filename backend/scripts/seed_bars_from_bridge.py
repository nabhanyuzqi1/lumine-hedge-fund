#!/usr/bin/env python3
"""
Seed bars manual dari MT5 bridge.

Script ini mengirim command ke EA untuk fetch bars langsung dari MT5 terminal
dan insert ke PostgreSQL. Workaround untuk EA yang tidak bisa compile.

Usage:
    python scripts/seed_bars_from_bridge.py [--tf 1m,5m,1h] [--limit 500]
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lumine.data.session import get_sessionmaker
from sqlalchemy import text


async def seed_bars_from_redis():
    """
    Check if bars already in Redis mt5:seed_bars queue.
    EA pushes bars here during seed phase.
    """
    try:
        from lumine.data.redis_client import get_redis
        r = await get_redis()
        
        # Check seed_bars queue
        bars_raw = await r.lrange("mt5:seed_bars", 0, -1)
        if bars_raw:
            print(f"[SEED] Found {len(bars_raw)} bars in mt5:seed_bars queue")
            return [json.loads(b) for b in bars_raw]
        
        # Check if bars already processed
        processed = await r.get("mt5:seed_bars_processed")
        if processed:
            print(f"[SEED] Bars already processed at {processed.decode()}")
            return None
            
        return None
    except Exception as e:
        print(f"[SEED] Error checking Redis: {e}")
        return None


async def insert_bars_to_db(bars_data: list, symbol: str = "XAUUSD"):
    """
    Insert bars from EA seed data to PostgreSQL.
    
    bars_data format:
    {
        "symbol": "XAUUSD",
        "timeframe": "1m",
        "bars": [
            {"ts": 1723628400, "open": 1.2345, "high": 1.2350, "low": 1.2340, "close": 1.2348, "volume": 100},
            ...
        ]
    }
    """
    if not bars_data:
        print("[SEED] No bars data to insert")
        return 0
    
    inserted = 0
    async with get_sessionmaker()() as session:
        for bar_packet in bars_data:
            tf = bar_packet.get("timeframe", "1m").lower()
            bars = bar_packet.get("bars", [])
            sym = bar_packet.get("symbol", symbol)
            
            if not bars:
                continue
            
            # Map timeframe to table
            tf_table_map = {
                "m1": "bars_1m",
                "5m": "bars_5m", 
                "15m": "bars_15m",
                "h1": "bars_1h",
                "h4": "bars_4h",
                "d1": "bars_1d",
            }
            table = tf_table_map.get(tf, f"bars_{tf}")
            
            for bar in bars:
                try:
                    ts = bar.get("ts")
                    if not ts:
                        continue
                    
                    # Convert Unix timestamp to datetime
                    if isinstance(ts, (int, float)):
                        ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    else:
                        continue
                    
                    # Insert with ON CONFLICT DO NOTHING
                    await session.execute(
                        text(f"""
                            INSERT INTO {table} (ts, symbol, open, high, low, close, volume)
                            VALUES (:ts, :symbol, :open, :high, :low, :close, :volume)
                            ON CONFLICT (ts, symbol) DO NOTHING
                        """),
                        {
                            "ts": ts_dt,
                            "symbol": sym,
                            "open": bar.get("open", 0),
                            "high": bar.get("high", 0),
                            "low": bar.get("low", 0),
                            "close": bar.get("close", 0),
                            "volume": bar.get("volume", 0) or bar.get("tick_volume", 0),
                        }
                    )
                    inserted += 1
                except Exception as e:
                    print(f"[SEED] Error inserting bar: {e}")
        
        await session.commit()
    
    return inserted


async def trigger_ea_seed():
    """
    Send SEED_BARS command to EA via Redis.
    EA should pick this up on next polling cycle.
    """
    try:
        from lumine.data.redis_client import get_redis
        r = await get_redis()
        
        # Send command to EA
        command = {
            "id": f"seed-{datetime.now().isoformat()}",
            "command": "SEED_BARS",
            "symbol": "XAUUSD",
            "timeframes": ["M1", "M5", "M15", "H1", "H4"],
            "limit": 500,
        }
        
        await r.rpush("mt5:commands", json.dumps(command))
        print(f"[SEED] Sent SEED_BARS command to EA: {command['id']}")
        return True
    except Exception as e:
        print(f"[SEED] Error sending command: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Seed bars from MT5 bridge")
    parser.add_argument("--tf", default="M1,M5,H1", help="Timeframes (comma-separated)")
    parser.add_argument("--limit", type=int, default=500, help="Bars per timeframe")
    parser.add_argument("--trigger", action="store_true", help="Trigger EA to seed")
    args = parser.parse_args()
    
    print(f"[SEED] Starting bars seed process")
    print(f"[SEED] Timeframes: {args.tf}")
    print(f"[SEED] Limit per TF: {args.limit}")
    
    # Option 1: Trigger EA to seed
    if args.trigger:
        await trigger_ea_seed()
        print("[SEED] Command sent. Wait 30s for EA to process, then run again without --trigger.")
        return
    
    # Option 2: Check for bars in Redis queue
    bars_data = await seed_bars_from_redis()
    
    if bars_data:
        inserted = await insert_bars_to_db(bars_data)
        print(f"[SEED] Inserted {inserted} bars to database")
    else:
        print("[SEED] No bars found in Redis. EA may not have seeded yet.")
        print("[SEED] Run with --trigger to send SEED_BARS command to EA.")
    
    # Show current DB state
    async with get_sessionmaker()() as session:
        for table in ["bars_1m", "bars_5m", "bars_1h"]:
            r = await session.execute(text(f"SELECT COUNT(*), MAX(ts) FROM {table}"))
            row = r.fetchone()
            print(f"[SEED] {table}: count={row[0]}, max_ts={row[1]}")


if __name__ == "__main__":
    asyncio.run(main())
