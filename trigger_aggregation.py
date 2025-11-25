"""
Manual trigger script for hourly aggregation job.
Run this inside the analytics workers container to test the aggregation immediately.
"""
import asyncio
import sys
import os

sys.path.insert(0, '/app')

import analytics_workers.config as config
import analytics_workers.database as database
import analytics_workers.jobs.aggregated_metrics as aggregated_metrics


async def main():
    print("Initializing database connections...")
    await database.init_db()

    print("Running hourly aggregation job...")
    await aggregated_metrics.aggregate_hourly_metrics()

    print("Closing database connections...")
    await database.close_db()

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
