from redis import Redis
r = Redis.from_url("redis://redis:6379/0")
print("Lock value:", r.get("weekly_pipeline_lock"))
print("TTL:", r.ttl("weekly_pipeline_lock"))
print("Deleted:", r.delete("weekly_pipeline_lock"))
