#!/usr/bin/env python3
"""
Database migration helper for adding tag filtering features
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import TagRule, Tag, ChannelTag, PlaylistConfig
from services.tag_service import TagService

def migrate_database():
    """Create new tables and initialize default data"""
    print("Starting database migration...")
    
    with app.app_context():
        # Create all tables
        print("Creating new tables...")
        db.create_all()
        print("✓ Tables created successfully")
        
        # Check if default rules already exist
        existing_rules = TagRule.query.count()
        
        if existing_rules == 0:
            print("\nCreating default tag extraction rules...")
            try:
                rules = TagService.create_default_rules(db.session)
                print(f"✓ Created {len(rules)} default tag rules")
            except Exception as e:
                print(f"✗ Error creating default rules: {e}")
        else:
            print(f"\n⚠ Found {existing_rules} existing tag rules, skipping default creation")
        
        print("\n" + "="*60)
        print("Database migration completed!")
        print("="*60)
        print("\nNext steps:")
        print("1. Process tags for your accounts:")
        print("   POST /api/accounts/<account_id>/process-tags")
        print("\n2. View extracted tags:")
        print("   GET /api/accounts/<account_id>/tags")
        print("\n3. Create playlist configurations:")
        print("   POST /api/playlist-configs")
        print("\n4. Generate playlists:")
        print("   GET /playlist/config/<config_id>.m3u")
        print("\nSee TAG_FILTERING_GUIDE.md for detailed documentation.")

if __name__ == '__main__':
    migrate_database()
