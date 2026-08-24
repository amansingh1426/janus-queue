"""Interactive & Visual Demonstration of Persistent Priority Queue.

Showcases:
1. Core Priority Queue Operations (Insert, Extract Min/Max, Peek, Update, Delete).
2. Persistence Across Process Restarts (WAL Replay + Snapshotting).
3. Real-World Use Case 1: Operating System Real-Time Job Scheduler (with Priority Boosting).
4. Real-World Use Case 2: Hospital Emergency Room Triage System.
"""

import os
import shutil
import time
from module import PersistentPriorityQueue


def print_banner(title: str):
    print("\n" + "=" * 70)
    print(f"  {title.upper()}")
    print("=" * 70)


def demo_core_operations():
    print_banner("1. Core Double-Ended Priority Queue Operations")
    demo_dir = "./demo_data_core"
    if os.path.exists(demo_dir):
        shutil.rmtree(demo_dir)

    pq = PersistentPriorityQueue(storage_dir=demo_dir, queue_name="core_demo")
    print(f"[*] Created new queue: {pq} | is_empty: {pq.is_empty()}")

    print("\n[+] Inserting 5 items with varying priorities:")
    tasks = [
        ("task_db_backup", 50.0, "Nightly database backup"),
        ("task_user_login", 2.0, "Process active user login request"),
        ("task_security_alert", 0.5, "DDoS mitigation rule trigger"),
        ("task_email_newsletter", 80.0, "Send weekly promotional emails"),
        ("task_payment_process", 1.0, "Credit card payment processing"),
    ]
    for tid, prio, desc in tasks:
        item = pq.insert(item_id=tid, priority=prio, data={"description": desc})
        print(f"    -> Inserted: '{tid}' with priority {prio} ({desc})")

    print(f"\n[*] Current Queue Size: {len(pq)}")
    print(f"[*] Peek Minimum (Highest Urgency): {pq.peek_min().item_id} (Priority: {pq.peek_min().priority})")
    print(f"[*] Peek Maximum (Lowest Urgency):  {pq.peek_max().item_id} (Priority: {pq.peek_max().priority})")

    print("\n[+] Updating Priority (Dynamic Priority Adjustment):")
    print("    Promoting 'task_email_newsletter' from priority 80.0 to 0.1 (Flash Sale Announcement!)")
    pq.update(item_id="task_email_newsletter", new_priority=0.1)
    print(f"    -> New Peek Minimum: '{pq.peek_min().item_id}' (Priority: {pq.peek_min().priority})")

    print("\n[+] Deleting an item directly:")
    print("    Deleting 'task_db_backup' (Cancelled by admin)...")
    deleted = pq.delete("task_db_backup")
    print(f"    -> Successfully deleted: '{deleted.item_id}'")

    print("\n[+] Extracting items in priority order:")
    print(f"    Extract Min: {pq.extract_min()}")
    print(f"    Extract Max: {pq.extract_max()}")
    print(f"    Extract Min: {pq.extract_min()}")

    print(f"\n[*] Remaining Items in Queue: {len(pq)}")
    pq.close()
    if os.path.exists(demo_dir):
        shutil.rmtree(demo_dir)


def demo_persistence_and_recovery():
    print_banner("2. Persistence & Crash Recovery Demonstration")
    demo_dir = "./demo_data_persistence"
    if os.path.exists(demo_dir):
        shutil.rmtree(demo_dir)

    print("[*] STEP 1: Creating Queue and persisting operations to disk...")
    pq1 = PersistentPriorityQueue(storage_dir=demo_dir, queue_name="durable_queue")
    pq1.insert("order_101", 10.0, data={"amount": "$45.00", "customer": "Alice"})
    pq1.insert("order_102", 2.0,  data={"amount": "$120.00", "customer": "Bob (VIP)"})
    pq1.insert("order_103", 5.0,  data={"amount": "$75.00", "customer": "Charlie"})
    pq1.insert("order_104", 1.0,  data={"amount": "$500.00", "customer": "Diana (Urgent)"})

    print(f"    Inserted 4 orders. Current Top Priority: {pq1.peek_min().item_id}")

    # Close/terminate session simulating process termination
    print("    [!] Simulating sudden application shutdown / restart...")
    pq1.close()
    del pq1

    print("\n[*] STEP 2: Reopening Queue from on-disk Write-Ahead Log (WAL)...")
    pq2 = PersistentPriorityQueue(storage_dir=demo_dir, queue_name="durable_queue")
    print(f"    -> Successfully recovered {len(pq2)} orders from disk!")

    print("\n[*] STEP 3: Draining recovered queue in exact priority order:")
    while not pq2.is_empty():
        item = pq2.extract_min()
        print(f"    -> Processed Order: ID={item.item_id:10} | Priority={item.priority:<4} | Data={item.data}")

    pq2.close()
    if os.path.exists(demo_dir):
        shutil.rmtree(demo_dir)


def demo_hospital_triage_use_case():
    print_banner("3. Real-World Use Case: Emergency Hospital Triage System")
    demo_dir = "./demo_data_triage"
    if os.path.exists(demo_dir):
        shutil.rmtree(demo_dir)

    pq = PersistentPriorityQueue(storage_dir=demo_dir, queue_name="er_triage")

    patients = [
        ("P_001", 3, {"name": "John Doe", "symptom": "Moderate ankle sprain", "acuity": "Urgent"}),
        ("P_002", 5, {"name": "Jane Smith", "symptom": "Mild rash", "acuity": "Non-urgent"}),
        ("P_003", 1, {"name": "Robert Taylor", "symptom": "Chest pain / cardiac arrest", "acuity": "Resuscitation"}),
        ("P_004", 2, {"name": "Emily Clark", "symptom": "Severe laceration", "acuity": "Emergent"}),
    ]

    print("[+] Admitting incoming patients to ER Triage Queue (Level 1=Highest Urgency):")
    for pid, prio, info in patients:
        pq.insert(item_id=pid, priority=prio, data=info)
        print(f"    Admitted {info['name']} (Acuity: {info['acuity']}, Priority: {prio})")

    print(f"\n[*] Next patient to see ER Physician: {pq.peek_min().data['name']}")

    print("\n[!] Condition Change Alert: Jane Smith (P_002) experiencing sudden anaphylaxis!")
    print("    Updating P_002 priority from 5 (Non-urgent) -> 0.5 (Critical Anaphylaxis)")
    pq.update("P_002", new_priority=0.5, new_data={"name": "Jane Smith", "symptom": "Acute Anaphylaxis", "acuity": "Critical"})

    print("\n[+] Attending physicians treating patients in order of urgency:")
    rank = 1
    while not pq.is_empty():
        treated = pq.extract_min()
        print(f"    #{rank}: Treating {treated.data['name']} (Priority: {treated.priority}) - {treated.data['symptom']}")
        rank += 1

    pq.close()
    if os.path.exists(demo_dir):
        shutil.rmtree(demo_dir)


if __name__ == "__main__":
    demo_core_operations()
    demo_persistence_and_recovery()
    demo_hospital_triage_use_case()
    print("\n" + "=" * 70)
    print("  ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY!")
    print("=" * 70 + "\n")
