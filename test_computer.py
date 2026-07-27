from app.computer.application_indexer import ApplicationIndexer
from app.computer.application_discovery.fingerprint_manager import FingerprintManager

indexer = ApplicationIndexer()
manager = FingerprintManager()

apps = indexer.load()

print("Changed:", manager.changed(apps))

manager.save(
    manager.generate(apps)
)

print("Fingerprint saved.")