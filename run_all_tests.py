#!/usr/bin/python3
# coding:utf-8
#
# by: Eric Chen (hchen@bluecatnetworks.com)
# python ver: python 3
# BAM ver: 26.1
#
# v1.0-20260921 created
#
# ---------------------------------------------------------------------------
# Test harness for the BAM v1->v2 CLI scripts in this directory.
#
# WHAT THIS DOES
#   Runs a scripted, self-cleaning lifecycle (add -> query -> update ->
#   delete, where applicable) against every CLI script this harness knows
#   how to exercise, against your LIVE BAM system (bamconfig.json in this
#   same folder). Every command's stdout/stderr/return code is captured to
#   a timestamped log file, and a summary table is printed at the end and
#   saved next to it.
#
# WHAT THIS DOES NOT DO
#   - It does not run debug_*.py (those are one-off diagnostics with
#     hardcoded values from earlier troubleshooting, not general scripts).
#   - It does not touch anything outside the CONFIG block below except
#     records it creates itself (all named with TEST_PREFIX) - it never
#     modifies pre-existing production records.
#   - Some scripts are gated OFF by default because they need environment
#     specifics this harness can't safely guess (an existing IP4Network,
#     a server safe to attach/detach a DNS role on, etc.) or because they
#     have a real side effect on shared infrastructure (deploy_server.py
#     actually pushes a deployment to a real server). Fill in the relevant
#     CONFIG value and flip the matching RUN_* flag to True to enable one.
#     See the "NOT COVERED BY DEFAULT" list printed at the end of a run.
#
# USAGE
#   python3 run_all_tests.py                 # interactive confirm, then run everything enabled
#   python3 run_all_tests.py --yes            # skip the confirmation prompt
#   python3 run_all_tests.py --list           # just list the planned steps, don't run anything
#   python3 run_all_tests.py --dry-run        # print each command instead of running it
#   python3 run_all_tests.py --only host      # only run steps whose id contains "host"
#   python3 run_all_tests.py --keep           # skip the cleanup/delete steps (leave test data behind)
#   python3 run_all_tests.py --timeout 60     # per-command timeout in seconds (default 30)
# ---------------------------------------------------------------------------

import argparse
import datetime
import os
import subprocess
import sys

CLI_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

# ===========================================================================
# CONFIG - edit these to match your BAM environment before running.
# Defaults below match the fixtures used throughout this project's own
# manual testing (config1/view1/red.corp, servers dds1/dds2/dds3/dds4).
# ===========================================================================
CONFIG_NAME = "config1"
VIEW_NAME = "view1"
ZONE_NAME = "red.corp"
SERVER_NAME = "dds1"          # used only for the read-only server_query.py check

# Every record this harness creates is named "<TEST_PREFIX><something>" so
# it's obvious at a glance which records came from this harness, and so it
# can never collide with a real record name.
TEST_PREFIX = "zzh"

# Disposable IPs used for A/host records this harness creates and deletes.
# Pick addresses in a range you know is safe to write test records against
# (they do NOT need to be real/pingable - BAM will happily store an address
# that isn't actually assigned to anything, but pick something in YOUR
# address space so a duplicate-IP conflict is unlikely).
TEST_IP_1 = "10.99.99.201"
TEST_IP_2 = "10.99.99.202"
TEST_IP_3 = "10.99.99.203"
TEST_IP_4 = "10.99.99.204"
TEST_IP_5 = "10.99.99.205"      # used by the HostRecord anchor (see Phase 1) - kept distinct from TEST_IP_1 to avoid a duplicate-IP conflict, since both anchors exist at the same time

# --- optional / gated blocks - fill in and flip the RUN_* flag to enable ---
RUN_IP_SPACE_TESTS = False      # ip4addr_*/dhcp4range_*/ip4network_* - needs a real network below
TEST_NETWORK_CIDR = ""          # e.g. "10.50.0.0/24" - must already exist in BAM
TEST_FREE_IP_1 = ""             # a currently-unassigned address inside TEST_NETWORK_CIDR
TEST_FREE_IP_2 = ""             # a second currently-unassigned address inside TEST_NETWORK_CIDR
DHCP_RANGE_START = ""           # a free sub-range inside TEST_NETWORK_CIDR, e.g. "10.50.0.240"
DHCP_RANGE_END = ""             # e.g. "10.50.0.250"

RUN_DNSROLE_TESTS = False       # dnsRole_* - touches a real server's DNS deployment role
DNSROLE_SERVER_NAME = ""        # a server you're OK adding/removing a "recursion" role on

RUN_DEPLOY_TESTS = False        # deploy_server.py/deploy_status.py - pushes a REAL deployment
DEPLOY_SERVER_NAME = ""

RUN_RPZ_TESTS = False           # rpz_add.py/rpz_update.py/rpz_delete.py/rpz_upload.py
RPZ_ZONE_NAME = ""              # an existing Response Policy Zone name
RPZ_UPLOAD_FILE = ""            # a local file path for rpz_upload.py

RUN_ACCESS_RIGHTS_TESTS = False # access_rights.py - needs an existing username
ACCESS_RIGHTS_USER = ""

RUN_MACPOOLITEM_TESTS = False    # macPoolItem_add/delete - needs a MAC already known to BAM
TEST_KNOWN_MAC = ""             # e.g. "00:11:22:33:44:55" - must already exist (a lease, reservation, or existing pool member)

# ===========================================================================
# Test plan
# ===========================================================================
# Each step: (id, script, args, note). Steps run strictly in the order
# listed - later steps in the same "group" depend on earlier ones having
# created the record they operate on.
CFG = ["-c", CONFIG_NAME]
VW = CFG + ["-v", VIEW_NAME]
ZN = VW + ["-z", ZONE_NAME]
P = TEST_PREFIX

STEPS = []


def add(step_id, script, args, note=""):
    STEPS.append({"id": step_id, "script": script, "args": [str(a) for a in args], "note": note})


# ---------------------------------------------------------------------
# Phase 0: read-only sanity checks (safe, no state change)
# ---------------------------------------------------------------------
add("config_query", "config_query.py", CFG)
add("view_query", "view_query.py", VW)
add("zone_query", "zone_query.py", ZN)
add("zone_query_all", "zone_query_all.py", VW + ["-a"])
add("server_query", "server_query.py", CFG + ["-s", SERVER_NAME])
add("zone_rr_query_all", "zone_rr_query.py", ZN + ["-a"])

# ---------------------------------------------------------------------
# Phase 1: create an anchor A record other record types can link to.
# Deleted at the very end (see the bottom of this file), not here.
# ---------------------------------------------------------------------
anchor_name = P + "anchor"
anchor_fqdn = "%s.%s" % (anchor_name, ZONE_NAME)
add("anchor_add", "a_add.py", ZN + ["-r", anchor_name, "-i", TEST_IP_1])
add("anchor_query", "a_query.py", ZN + ["-r", anchor_name])

# A second anchor, specifically a HostRecord (not a plain "A"/GenericRecord
# like the one above). CONFIRMED live: a CNAME/SRV/AliasRecord's
# 'linkedRecord' target must be a real HostRecord (or a few other types -
# see LINKABLE_RECORD_TYPES in BAM.py) - pointing one at a plain "A" record
# added via a_add.py 400s with InvalidResourceType, even though the same
# name/IP added via host_add.py works immediately. Used below by
# cname_add/cname_update and srv_add/srv_update.
host_anchor_name = P + "hostanchor"
host_anchor_fqdn = "%s.%s" % (host_anchor_name, ZONE_NAME)
add("host_anchor_add", "host_add.py", ZN + ["-r", host_anchor_name, "-i", TEST_IP_5])

# ---------------------------------------------------------------------
# Phase 2: A record lifecycle (independent of the anchor)
# ---------------------------------------------------------------------
a1 = P + "a1"
add("a_add", "a_add.py", ZN + ["-r", a1, "-i", TEST_IP_2])
add("a_query", "a_query.py", ZN + ["-r", a1])
add("a_update", "a_update.py", ZN + ["-r", a1, "-i", TEST_IP_2, "--ni", TEST_IP_3])
add("a_delete", "a_delete.py", ZN + ["-r", a1, "-i", TEST_IP_3])

# ---------------------------------------------------------------------
# Phase 3: CNAME lifecycle (points at the anchor)
# ---------------------------------------------------------------------
cname1 = P + "cname1"
add("cname_add", "cname_add.py", ZN + ["-r", cname1, "-i", host_anchor_fqdn])
add("cname_query", "cname_query.py", ZN + ["-r", cname1])
add("cname_update", "cname_update.py", ZN + ["-r", cname1, "--ni", host_anchor_fqdn])
add("cname_delete", "cname_delete.py", ZN + ["-r", cname1])

# ---------------------------------------------------------------------
# Phase 4: HOST record lifecycle (host_add/query/update/delete)
# ---------------------------------------------------------------------
host1 = P + "host1"
add("host_add", "host_add.py", ZN + ["-r", host1, "-i", TEST_IP_2])
add("host_query", "host_query.py", ZN + ["-r", host1])
add("host_update", "host_update.py", ZN + ["-r", host1, "-i", TEST_IP_2 + "," + TEST_IP_3])
add("host_delete", "host_delete.py", ZN + ["-r", host1])

# ---------------------------------------------------------------------
# Phase 5: HOST one-IP-at-a-time lifecycle (host_add_one/update_one/delete_one)
# ---------------------------------------------------------------------
host2 = P + "host2"
add("host2_add", "host_add.py", ZN + ["-r", host2, "-i", TEST_IP_2])
add("host_add_one", "host_add_one.py", ZN + ["-r", host2, "-i", TEST_IP_3])
add("host_update_one", "host_update_one.py", ZN + ["-r", host2, "-i", TEST_IP_3, "--ni", TEST_IP_4])
add("host_delete_one", "host_delete_one.py", ZN + ["-r", host2, "-i", TEST_IP_4])
add("host2_delete", "host_delete.py", ZN + ["-r", host2])

# ---------------------------------------------------------------------
# Phase 6: NS record lifecycle (points at the anchor)
# ---------------------------------------------------------------------
ns1 = P + "ns1"
add("ns_add", "ns_add.py", ZN + ["-r", ns1, "-i", anchor_fqdn])
add("ns_query", "ns_query.py", ZN + ["-r", ns1])
add("ns_update", "ns_update.py", ZN + ["-r", ns1, "-i", anchor_fqdn, "--ni", anchor_fqdn])
add("ns_delete", "ns_delete.py", ZN + ["-r", ns1, "-i", anchor_fqdn])

# ---------------------------------------------------------------------
# Phase 7: SRV record lifecycle (points at the anchor)
# ---------------------------------------------------------------------
srv1 = P + "srv1"
add("srv_add", "srv_add.py", ZN + ["-r", srv1, "-i", host_anchor_fqdn, "-o", "10", "-p", "5060", "-w", "100"])
add("srv_query", "srv_query.py", ZN + ["-r", srv1])
# srv_update.py always sets ALL fields to their "new" (--n*) counterparts,
# defaulting any omitted one to blank - so every --n* flag must be given
# even when only one field (port) is actually changing, or it'll blank out
# the others (same pattern fixed below for naptr_update).
add("srv_update", "srv_update.py", ZN + ["-r", srv1, "-i", host_anchor_fqdn, "-o", "10", "-p", "5060", "-w", "100",
                                          "--ni", host_anchor_fqdn, "--no", "10", "--np", "5061", "--nw", "100"])
add("srv_delete", "srv_delete.py", ZN + ["-r", srv1, "-i", host_anchor_fqdn, "-o", "10", "-p", "5061", "-w", "100"])

# ---------------------------------------------------------------------
# Phase 8: NAPTR record lifecycle
# ---------------------------------------------------------------------
naptr1 = P + "naptr1"
naptr_common = ["-g", "S", "-o", "100", "-p", "10",
                "-e", "!^.*$!sip:user@sip.rfc1035.com!",
                "-t", anchor_fqdn, "-s", "x-3gpp-pgw:x-gp:x-gn"]
add("naptr_add", "naptr_add.py", ZN + ["-r", naptr1] + naptr_common)
add("naptr_query", "naptr_query.py", ZN + ["-r", naptr1])
# naptr_update.py always sets ALL fields to their "new" (--n*) counterparts,
# defaulting any omitted one to an EMPTY STRING - so every --n* flag must be
# given even when only one field (order) is actually changing, or it blanks
# out the others (confirmed live: omitting --nt blanked 'replacement',
# which the server then rejected as "not a valid fully qualified domain
# name" - not a v1->v2 migration bug, just this script's existing
# all-fields-required update semantics).
naptr_new_common = ["--ng", "S", "--no", "999", "--np", "10",
                     "--ne", "!^.*$!sip:user@sip.rfc1035.com!",
                     "--nt", anchor_fqdn, "--ns", "x-3gpp-pgw:x-gp:x-gn"]
add("naptr_update", "naptr_update.py", ZN + ["-r", naptr1] + naptr_common + naptr_new_common)
naptr_common_after_update = naptr_common[:2] + ["-o", "999"] + naptr_common[4:]
add("naptr_delete", "naptr_delete.py", ZN + ["-r", naptr1] + naptr_common_after_update)
# NOTE: naptr_delete must match the record's CURRENT (post-update) order=999,
# not the original 100 - naptr_common[2:4] is ["-o","100"], replaced here
# with ["-o","999"] to match what naptr_update actually left behind.

# ---------------------------------------------------------------------
# Phase 9: generic TXT record lifecycle (no dedicated txt_*.py - this is
# the intended path for TXT/HINFO/MX/etc.)
# ---------------------------------------------------------------------
txt1 = P + "txt1"
add("generic_add_txt", "generic_add.py", ZN + ["-r", txt1, "-t", "txt", "-i", "harness test record"])
add("generic_query_txt", "generic_query.py", ZN + ["-r", txt1, "-t", "TXT"])
add("generic_update_txt", "generic_update.py",
    ZN + ["-t", "TXT", "-r", txt1, "-i", "harness test record", "--ni", "harness test record v2"])
add("generic_delete_txt", "generic_delete.py",
    ZN + ["-r", txt1, "-t", "txt", "-i", "harness test record v2"])

# ---------------------------------------------------------------------
# Phase 10: view-level match-clients ACL lifecycle
# ---------------------------------------------------------------------
add("matchClient_add", "matchClient_add.py", VW + ["-m", "203.0.113.0/24"])
add("matchClient_query", "matchClient_query.py", VW)
add("matchClient_update", "matchClient_update.py", VW + ["-m", "203.0.113.0/24,198.51.100.0/24"])
add("matchClient_delete", "matchClient_delete.py", VW)

# ---------------------------------------------------------------------
# Phase 11: config-level DNS forwarding lifecycle
# ---------------------------------------------------------------------
add("dns_forwarding_add", "dns_forwarding_add.py", CFG + ["-i", "198.51.100.53", "-z", "yes"])
add("dns_forwarding_query", "dns_forwarding_query.py", CFG)
add("dns_forwarding_delete", "dns_forwarding_delete.py", CFG)

# ---------------------------------------------------------------------
# Phase 12: config-level DNS forwarding-POLICY lifecycle (no query script
# exists for this one)
# ---------------------------------------------------------------------
add("dns_forwardingPolicy_add", "dns_forwardingPolicy_add.py", CFG + ["-o"])
add("dns_forwardingPolicy_delete", "dns_forwardingPolicy_delete.py", CFG)

# ---------------------------------------------------------------------
# Phase 13: MAC pool lifecycle. macPoolItem_add/delete are deliberately
# NOT included here by default - CONFIRMED live: macPoolItem_add.py
# requires the MAC address to already exist as a known entity in the
# configuration (via bam.getMACAddress()) BEFORE it can be associated with
# a pool - it does not register a brand-new MAC on the fly. A made-up MAC
# that's never been seen (e.g. via a DHCP lease or an existing pool/deny
# entry) will always fail this pre-check with "does not exist", regardless
# of the v1->v2 migration - this is existing BAM/script behavior, not
# something this harness can safely fake. Fill in TEST_KNOWN_MAC below
# with a MAC address that's already registered in your configuration (any
# existing lease, reservation, or pool member) and flip
# RUN_MACPOOLITEM_TESTS to True to exercise this path.
# ---------------------------------------------------------------------
pool1 = P + "pool1"
add("macPool_add", "macPool_add.py", CFG + ["-p", pool1])
add("macPool_query", "macPool_query.py", CFG + ["-p", pool1])
if RUN_MACPOOLITEM_TESTS and TEST_KNOWN_MAC:
    add("macPoolItem_add", "macPoolItem_add.py", CFG + ["-p", pool1, "-m", TEST_KNOWN_MAC])
    add("macPoolItem_delete", "macPoolItem_delete.py", CFG + ["-p", pool1, "-m", TEST_KNOWN_MAC])
add("macPool_delete", "macPool_delete.py", CFG + ["-p", pool1])

# ---------------------------------------------------------------------
# Phase 14: delete the anchors created in Phase 1
# ---------------------------------------------------------------------
add("anchor_delete", "a_delete.py", ZN + ["-r", anchor_name, "-i", TEST_IP_1])
add("host_anchor_delete", "host_delete.py", ZN + ["-r", host_anchor_name])

# ---------------------------------------------------------------------
# Optional / gated phases - only added to the plan if enabled above.
# ---------------------------------------------------------------------
if RUN_IP_SPACE_TESTS and TEST_NETWORK_CIDR and TEST_FREE_IP_1 and TEST_FREE_IP_2:
    add("ip4network_query", "ip4network_query.py", CFG + ["-b", TEST_NETWORK_CIDR])
    add("ip4addr_add", "ip4addr_add.py", CFG + ["-i", TEST_FREE_IP_1, "-n", P + "ipaddr1", "-s"])
    add("ip4addr_query", "ip4addr_query.py", CFG + ["-i", TEST_FREE_IP_1])
    add("ip4addr_update", "ip4addr_update.py", CFG + ["-i", TEST_FREE_IP_1, "-n", P + "ipaddr1-renamed"])
    add("ip4addr_udf_update", "ip4addr_udf_update.py", CFG + ["-i", TEST_FREE_IP_1])
    add("ip4addr_delete", "ip4addr_delete.py", CFG + ["-i", TEST_FREE_IP_1])
    if DHCP_RANGE_START and DHCP_RANGE_END:
        add("dhcp4range_add", "dhcp4range_add.py",
            CFG + ["-b", TEST_NETWORK_CIDR, "-s", DHCP_RANGE_START, "-e", DHCP_RANGE_END, "-n", P + "range1"])
        add("dhcp4range_query", "dhcp4range_query.py", CFG + ["-b", TEST_NETWORK_CIDR])
        add("dhcp4range_update", "dhcp4range_update.py",
            CFG + ["-b", TEST_NETWORK_CIDR, "-s", DHCP_RANGE_START, "-e", DHCP_RANGE_END, "-n", P + "range1-renamed"])
        add("dhcp4range_delete", "dhcp4range_delete.py",
            CFG + ["-b", TEST_NETWORK_CIDR, "-s", DHCP_RANGE_START, "-e", DHCP_RANGE_END])

if RUN_DNSROLE_TESTS and DNSROLE_SERVER_NAME:
    add("dnsRole_add", "dnsRole_add.py", ZN + ["-r", "recursion", "-s", DNSROLE_SERVER_NAME])
    add("dnsRole_query", "dnsRole_query.py", ZN + ["-s", DNSROLE_SERVER_NAME])
    add("dnsRole_update", "dnsRole_update.py", ZN + ["-s", DNSROLE_SERVER_NAME, "--nr", "forwarder"])
    add("dnsRole_delete", "dnsRole_delete.py", ZN + ["-r", "forwarder", "-s", DNSROLE_SERVER_NAME])

if RUN_DEPLOY_TESTS and DEPLOY_SERVER_NAME:
    add("deploy_server", "deploy_server.py", CFG + ["-s", DEPLOY_SERVER_NAME])
    add("deploy_status", "deploy_status.py", CFG + ["-s", DEPLOY_SERVER_NAME])

if RUN_RPZ_TESTS and RPZ_ZONE_NAME:
    add("rpz_add", "rpz_add.py", CFG + ["-z", RPZ_ZONE_NAME, "-r", P + "rpz1", "-a", "10.99.99.210"])
    add("rpz_update", "rpz_update.py", CFG + ["-z", RPZ_ZONE_NAME, "-r", P + "rpz1", "-a", "10.99.99.211"])
    add("rpz_delete", "rpz_delete.py", CFG + ["-z", RPZ_ZONE_NAME, "-r", P + "rpz1"])
    if RPZ_UPLOAD_FILE:
        add("rpz_upload", "rpz_upload.py", CFG + ["-z", RPZ_ZONE_NAME, "-f", RPZ_UPLOAD_FILE])

if RUN_ACCESS_RIGHTS_TESTS and ACCESS_RIGHTS_USER:
    add("access_rights_query", "access_rights.py", CFG + ["-u", ACCESS_RIGHTS_USER])

# Scripts this harness deliberately does NOT wire up at all (syntax not
# fully verified against a live run, or purely informational/utility) -
# shown in the end-of-run summary so nothing is silently missing.
NOT_COVERED = [
    "server_role.py (server role assignment - syntax not verified live)",
    "mac_query.py (generic MAC search - syntax not verified live)",
    "dump_rr.py (full recursive config dump - slow, better run manually)",
    "cli.py / log.py / password.py (utility modules, not standalone commands)",
]


# ===========================================================================
# Runner
# ===========================================================================
def run_step(step, timeout):
    script_path = os.path.join(CLI_DIR, step["script"])
    cmd = [PYTHON, script_path] + step["args"]
    started = datetime.datetime.now()
    try:
        proc = subprocess.run(
            cmd, cwd=CLI_DIR, capture_output=True, text=True,
            errors="replace", timeout=timeout,
        )
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or "")
        stderr = (e.stderr or "") + "\n[TIMED OUT after %ss]" % timeout
        rc = None
        timed_out = True
    elapsed = (datetime.datetime.now() - started).total_seconds()

    combined = (stdout or "") + (stderr or "")
    has_error_line = "ERROR:" in combined
    if timed_out:
        status = "TIMEOUT"
    elif rc == 0 and not has_error_line:
        status = "PASS"
    elif rc == 0 and has_error_line:
        status = "WARN"   # exited 0 but printed an ERROR: line - worth a look
    else:
        status = "FAIL"
    return {
        "id": step["id"], "cmd": cmd, "rc": rc, "stdout": stdout, "stderr": stderr,
        "status": status, "elapsed": elapsed,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    ap.add_argument("--list", action="store_true", help="list planned steps and exit")
    ap.add_argument("--dry-run", action="store_true", help="print commands instead of running them")
    ap.add_argument("--only", default=None, help="only run steps whose id contains this substring")
    ap.add_argument("--keep", action="store_true", help="skip *_delete/*_udf_update-style cleanup steps")
    ap.add_argument("--timeout", type=int, default=30, help="per-command timeout in seconds (default 30)")
    args = ap.parse_args()

    plan = STEPS
    if args.only:
        plan = [s for s in plan if args.only.lower() in s["id"].lower()]
    if args.keep:
        plan = [s for s in plan if "delete" not in s["id"].lower()]

    if args.list or args.dry_run:
        for s in plan:
            print("[%s] %s %s" % (s["id"], s["script"], " ".join(s["args"])))
        if args.list:
            print("\n%d steps planned. NOT covered by this harness:" % len(plan))
            for n in NOT_COVERED:
                print("  - %s" % n)
            return
        if args.dry_run:
            return

    print("This will run %d live commands against the BAM server in bamconfig.json," % len(plan))
    print("creating and deleting disposable records prefixed '%s' in zone '%s'." % (TEST_PREFIX, ZONE_NAME))
    if not args.yes:
        resp = input("Type 'yes' to proceed: ").strip().lower()
        if resp != "yes":
            print("Aborted.")
            return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(CLI_DIR, "test_run_%s.log" % ts)
    summary_path = os.path.join(CLI_DIR, "test_run_%s_summary.txt" % ts)

    results = []
    with open(log_path, "w", encoding="utf-8") as log:
        for i, step in enumerate(plan, 1):
            print("[%d/%d] %-24s " % (i, len(plan), step["id"]), end="", flush=True)
            result = run_step(step, args.timeout)
            results.append(result)
            print("%s (%.1fs)" % (result["status"], result["elapsed"]))

            log.write("=" * 78 + "\n")
            log.write("STEP: %s\n" % step["id"])
            log.write("CMD:  %s\n" % " ".join(result["cmd"]))
            log.write("RC:   %s   STATUS: %s   ELAPSED: %.1fs\n" % (result["rc"], result["status"], result["elapsed"]))
            log.write("--- stdout ---\n%s\n" % (result["stdout"] or "(empty)"))
            log.write("--- stderr ---\n%s\n\n" % (result["stderr"] or "(empty)"))

    # summary
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines = []
    lines.append("Test run %s - %d steps" % (ts, len(results)))
    lines.append("  ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())))
    lines.append("")
    for r in results:
        lines.append("%-8s %-24s rc=%-5s %.1fs" % (r["status"], r["id"], r["rc"], r["elapsed"]))
    lines.append("")
    lines.append("NOT covered by this harness (run manually if needed):")
    for n in NOT_COVERED:
        lines.append("  - %s" % n)
    summary_text = "\n".join(lines)

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)

    print("\n" + summary_text)
    print("\nFull output for every step: %s" % log_path)
    print("This summary:                %s" % summary_path)


if __name__ == "__main__":
    main()
