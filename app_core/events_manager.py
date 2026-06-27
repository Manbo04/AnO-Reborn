import json
import os
from typing import List, Dict, Optional

class EventsManager:
    """
    Manages loading and querying of interactive events for the News tab.
    """
    def __init__(self, events_file: str = 'events.json'):
        self.events: List[Dict] = []
        self.events_by_id: Dict[str, Dict] = {}
        self._load_events(events_file)

    def _load_events(self, events_file: str) -> None:
        """
        Loads the events from the specified JSON file into memory.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, events_file)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.events = json.load(f)
                self.events_by_id = {event['id']: event for event in self.events}
        except FileNotFoundError:
            print(f"Warning: Events file {file_path} not found. Starting with empty events.")
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse events JSON: {e}")
        except Exception as e:
            print(f"Error: An unexpected error occurred while loading events: {e}")

    def get_event(self, event_id: str) -> Optional[Dict]:
        """
        Retrieves a specific event by its ID.
        """
        return self.events_by_id.get(event_id)

    def get_all_events(self) -> List[Dict]:
        """
        Returns all loaded events.
        """
        return self.events
