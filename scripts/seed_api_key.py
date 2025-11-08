#!/usr/bin/env python3
"""Utility script to insert a development API key into MongoDB."""

import argparse

from services.mongo import create_mongo_client, get_database


def main():
    parser = argparse.ArgumentParser(description="Insert API key into MongoDB")
    parser.add_argument("apikey", help="API key to insert")
    parser.add_argument("email", nargs="?", default="dev@example.com")
    args = parser.parse_args()

    client = create_mongo_client()
    db = get_database(client)
    doc = {"apikey": args.apikey, "email": args.email}
    db["api_keys"].update_one({"apikey": args.apikey}, {"$set": doc}, upsert=True)
    print(f"API key {args.apikey} stored")


if __name__ == "__main__":
    main()
