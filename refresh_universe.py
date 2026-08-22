from data_sources import refresh_universe
if __name__=='__main__':
    u=refresh_universe(); print(f"Universe refreshed: {u['meta']['count']} stocks at {u['meta']['updated_at']}")
