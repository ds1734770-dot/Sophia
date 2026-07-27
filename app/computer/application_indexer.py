# import json
# from pathlib import Path
# import os
# from app.settings.paths import APPLICATION_DATABASE
# from app.computer.application_normalizer import ApplicationNormalizer
# from app.computer.application_discovery.start_menu_scanner import StartMenuScanner
# from app.computer.application_discovery.discovery_manager import DiscoveryManager


# class ApplicationIndexer:

#     def __init__(self):

#         self.database = APPLICATION_DATABASE
#         self.discovery = DiscoveryManager()

#     # ----------------------------

#     def build(self):

#         return self.discovery.discover()
#     # ----------------------------

#     def save(self, applications):

#         self.database.parent.mkdir(
#             parents=True,
#             exist_ok=True
#         )
    
#         with open(
#             self.database,
#             "w",
#             encoding="utf-8"
#         ) as f:
    
#             json.dump(
#                 applications,
#                 f,
#                 indent=4
#             )
    
#         return len(applications)
#     # ----------------------------

#     def load(self):

#         if not self.database.exists():
#             return []

#         with open(
#             self.database,
#             "r",
#             encoding="utf-8"
#         ) as f:

#             return json.load(f)

#     # ----------------------------

#     def initialize(self):

#         if not self.database.exists():

#             count = self.save()

#             print(f"[ApplicationIndexer] Indexed {count} applications.")

#     # ----------------------------

#     # def search(self, name):

#     #     applications = self.load()

#     #     name = name.lower().strip()

#     #     results = []

#     #     # Exact Match
#     #     for app in applications:

#     #         if app["name"].lower() == name:

#     #             return True, [app]

#     #     # Partial Match
#     #     for app in applications:

#     #         if name in app["name"].lower():

#     #             results.append(app)

#     #     if results:

#     #         return True, results

#     #     return False, "No matching applications found."

import json

from app.settings.paths import APPLICATION_DATABASE
from app.computer.application_discovery.discovery_manager import DiscoveryManager


class ApplicationIndexer:

    def __init__(self):

        self.database = APPLICATION_DATABASE
        self.discovery = DiscoveryManager()

    # ----------------------------

    def build(self):

        return self.discovery.discover()

    # ----------------------------

    def save(self, applications):

        self.database.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            self.database,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                applications,
                f,
                indent=4
            )

        return len(applications)

    # ----------------------------

    def load(self):

        if not self.database.exists():
            return []

        with open(
            self.database,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    # ----------------------------

    def initialize(self):

        if not self.database.exists():

            applications = self.build()

            count = self.save(applications)

            print(f"[ApplicationIndexer] Indexed {count} applications.")