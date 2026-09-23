#!/usr/bin/python
#coding:utf-8
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
# Copyright 2021 BlueCat Networks. This software is released under an
# OSI-approved license, the Python Software License 2.0. This license is
# incorporated by reference. The license grants you certain rights.
# https://opensource.org/licenses/Python-3.0
#
# ============================================================================
# v2-MIGRATION NOTICE
# ============================================================================
# This is a drop-in replacement for the original v1 (Services/REST/v1) BAM.py.
# It keeps the exact same class name (BAM), the exact same public method
# names and call signatures, and the exact same module-level helper functions
# (print_log, load_config, bam_logout, get_input_cmd, process_password,
# encrypt_password, decrypt_password, getLogger, getHtmlTitle) that every
# script in this project (cli.py + ~65 command scripts) already imports and
# calls. Internally, every method now talks to Address Manager's RESTful v2
# API (/api/v2/...) instead of the legacy v1 API (/Services/REST/v1/...).
#
# Because every script only ever talks to BlueCat through this module (never
# building v1 URLs itself), swapping this one file is enough to move the
# whole toolkit to v2 with zero or near-zero changes to the ~65 scripts.
#
# Reference: BlueCat Address Manager RESTful v2 API Guide (v26.1) -
#   https://docs.bluecatnetworks.com/r/en-US/Address-Manager-RESTful-v2-API-Guide/26.1.0
#
# HOW THE v1 -> v2 TRANSLATION WORKS
# -----------------------------------------------------------------------
# v1 exposed one bespoke RPC-style method per operation (addHostRecord,
# getEntityByName, etc.) keyed by parentId + type strings. v2 exposes typed,
# hierarchical resource collections (e.g. /api/v2/configurations/100881/views)
# navigated via HAL "_links" on every resource. To keep every v1-style
# (parentId, type) call working, this shim:
#   1. Resolves any entity by its bare numeric id via the v2 "root search"
#      endpoint: GET /api/v2?filter=id:{id} - this returns the resource
#      (with its own _links), regardless of what type it is.
#   2. Looks up the v2 collection name (e.g. "views", "zones",
#      "resourceRecords") that corresponds to a v1 "type" string via the
#      TYPE_LINK_KEY table below, then follows that key in the parent's
#      _links to get the actual v2 collection URL - so this module never has
#      to hardcode full REST paths per type combination.
#   3. Reshapes every v2 JSON resource back into the {id, name, type,
#      properties} shape the v1 API returned (see _v2_to_v1()), encoding
#      every other v2 field into the same pipe-delimited "properties" string
#      v1 used - so splitProp()/joinProp() and every script that calls them
#      keep working completely unchanged.
#
# KNOWN LIMITATIONS / THINGS TO VERIFY AGAINST YOUR SERVER
# -----------------------------------------------------------------------
# This shim was written from BlueCat's prose API guide and the official
# v1->v2 migration table, not from the live OpenAPI/Swagger schema (which
# has the authoritative field names for every resource type). The following
# are best-effort translations and are flagged inline with "VERIFY:" comments
# - test them against a real Address Manager v9.5+/v26.1 server and adjust
# field names using the interactive Swagger UI at
# http://{Address_Manager_IP}/api/docs if anything 400s:
#   - addAliasRecord/addSRVRecord field names (linkedRecord,
#     priority/port/weight) - confirm against the ResourceRecord schema
#     in Swagger. addNAPTRRecord's order/preference/service/replacement/flags
#     confirmed live via debug_naptr.py; 'regexp' is NOT a real v2 field -
#     it's 'regularExpression' (see V1_PROP_FIELD_ALIAS). addTXTRecord's
#     'txt' is NOT a real v2 field either - it's 'text' (confirmed live
#     via debug_txt.py, see V1_PROP_FIELD_ALIAS).
#   - addZone with a multi-label absoluteName (e.g. "test.corp") in one call
#     - v1 could do this in one shot; v2 may require creating "corp" then
#     "test" as a child zone depending on server version.
#   - getMACAddress/denyMACAddress/associateMACAddressWithPool field names.
#   - DNS/DHCP deployment role & option field names (serverInterface,
#     server, value).
#   - getServerDeploymentStatus's return shape (v1 returned a raw status
#     string; this returns the latest deployment record as JSON text).
#
# ALSO FIXED: the original v1 BAM.py's assignNextAvailableIP4Address() had a
# copy-paste bug (it referenced undefined names address1/address2/type
# instead of its own parameters, so it would have raised NameError if ever
# called). That bug is fixed here.
# ============================================================================

import requests
import json
import re
import os
import sys
import base64
import logging
import logging.handlers
import getpass

# global parameter to be used in getLogger() to define log format. If HW_project, will print vDNS
HW_project = False
Card_project = False


# ----------------------------------------------------------------------------
# v1 "type" string -> v2 HAL _links collection key.
# Used by every generic entity method (getEntityByName, getEntities,
# getEntitiesByName, addEntity, getLinkedEntities, etc.) to navigate the v2
# hierarchy the same way v1's opaque parentId/type pairs did, without having
# to hardcode a full REST path for every type.
# ----------------------------------------------------------------------------
TYPE_LINK_KEY = {
    "Configuration": "configurations",
    "View": "views",
    "Zone": "zones",
    "IP4Block": "blocks", "IPv4Block": "blocks",
    "IP6Block": "blocks", "IPv6Block": "blocks",
    "IP4Network": "networks", "IPv4Network": "networks",
    "IP6Network": "networks", "IPv6Network": "networks",
    "IP4Address": "addresses", "IPv4Address": "addresses",
    "IP6Address": "addresses", "IPv6Address": "addresses",
    "DHCP4Range": "ranges", "DHCP6Range": "ranges", "Range": "ranges",
    "MACPool": "macPools",
    "MACAddress": "macAddresses",
    "Server": "servers",
    # CONFIRMED live (dns_forwardingPolicy_add.py -g sg1: getEntities()
    # silently returned [] because "ServerGroup" had no TYPE_LINK_KEY entry
    # at all, hitting _link_key()'s ValueError -> getEntities()'s "no such
    # sub-collection" empty-list fallback, which then surfaced as a
    # misleading "serverGroup name not found" instead of a real error).
    # Same plural-collection-name pattern as every other entry here
    # (Server->servers, UserGroup->userGroups, etc.) - not yet separately
    # confirmed against a live 400, so re-check this key if it 404s.
    "ServerGroup": "serverGroups",
    "User": "users",
    "UserGroup": "userGroups",
    "Tag": "tags", "TagGroup": "tagGroups",
    "AccessRight": "accessRights",
    "DeploymentRole": "deploymentRoles",
    "DNSDeploymentRole": "deploymentRoles",
    "DHCPDeploymentRole": "deploymentRoles",
    "DeploymentOption": "deploymentOptions",
    "DNSDeploymentOption": "deploymentOptions",
    "DHCPDeploymentOption": "deploymentOptions",
    "DHCPServiceDeploymentOption": "deploymentOptions",
    "ResponsePolicy": "responsePolicies",
    "ResponsePolicyItem": "policyItems",
    "TFTPGroup": "tftpGroups",
    "DeviceType": "deviceTypes",
    "ClientClass": "clientClasses", "DHCPMatchClass": "clientClasses",
    # CONFIRMED live (debug_server.py): v1's per-server 'fullHostName'/
    # 'defaultInterfaceAddress'/'servicesIPv4Address' properties actually
    # live on a separate NetworkInterface sub-resource under the server
    # (v2's real type name is "NetworkInterface", not "NetworkServerInterface"
    # - but scripts pass the v1 name in purely to resolve the collection
    # link, same as the CNAMERecord/AliasRecord situation above, so it's
    # fine to map it here even though it isn't the real v2 type enum value).
    "NetworkServerInterface": "interfaces",
    # CONFIRMED live (debug_publishedinterface.py): a v2 "PublishedInterface"
    # (dnsRole_add.py's -p option resolves via v1's "PublishedServerInterface"
    # type name) lives in the exact SAME "interfaces" sub-collection as a
    # plain NetworkInterface under a server - a global type:'PublishedInterface'
    # search's result showed "collection": ".../servers/{id}/interfaces",
    # not a separate collection - so this maps to the same link key.
    "PublishedServerInterface": "interfaces",
    # DNS resource records all share the same v2 "resourceRecords" sub-collection
    "HostRecord": "resourceRecords",
    "GenericRecord": "resourceRecords",
    "AliasRecord": "resourceRecords",
    # NOTE: NOT a real v2 type enum value (CONFIRMED live via cname_add.py's
    # InvalidResourceType error, whose acceptedTypes list has "AliasRecord"
    # but no "CNAMERecord") - kept here only in case some script passes
    # this v1-ish alternate name in as a *type string* for collection-key
    # resolution (which still works fine, since this table is just about
    # picking "resourceRecords"), but see LINKABLE_RECORD_TYPES below for
    # the real enum values - never use this table for a type:in(...) or
    # request-body "type" field.
    "CNAMERecord": "resourceRecords",
    "MXRecord": "resourceRecords",
    "TXTRecord": "resourceRecords",
    "SRVRecord": "resourceRecords",
    "NAPTRRecord": "resourceRecords",
    "HINFORecord": "resourceRecords",
    "ExternalHostRecord": "resourceRecords",
}

# CONFIRMED live (zone_rr_query.py -t srv returned every record type in the
# zone, not just SRV records): unlike v1, where getEntities(zoneId,
# "SRVRecord", ...) filtered server-side by type, v2's resourceRecords
# collection is shared by every DNS record type and returns them all
# unfiltered - every v1 type below needs a server-side filter (see
# V1_RRTYPE_TO_RECORDTYPE_FILTER just below) to keep "only give me SRV
# records" working like it did against v1. Listed here purely for
# reference/documentation of which v1 types share the one collection.
RESOURCE_RECORD_TYPES = frozenset(
    t for t, key in TYPE_LINK_KEY.items() if key == "resourceRecords"
)
# CONFIRMED live: resourceRecords can NOT be filtered on 'type' at all (a
# 400 InvalidFilterField listed the real supported fields, which include
# 'recordType' instead) - and 'recordType' itself holds a SHORT form, not
# the v1 'XxxRecord' string (debug_naptr.py/debug_txt.py/debug_srv.py
# confirmed NAPTRRecord->'NAPTR', TXTRecord->'TXT', SRVRecord->'SRV', i.e.
# just the v1 name with the trailing 'Record' stripped). Only put a v1 type
# here once its recordType value has been confirmed live via
# debug_rrtypes.py - an unconfirmed/wrong value 400s just like 'type' did,
# so a v1 type NOT in this table deliberately gets NO server-side filter
# (falls back to returning everything, same as before this whole fix - not
# a regression, just not-yet-optimized) rather than guessing.
V1_RRTYPE_TO_RECORDTYPE_FILTER = {
    "SRVRecord": "SRV",
    "TXTRecord": "TXT",
    "NAPTRRecord": "NAPTR",
    # CONFIRMED live via debug_rrtypes.py.
    "AliasRecord": "CNAME",
    # NOTE: HostRecord's recordType came back None in debug_rrtypes.py (it's
    # simply not set on that type) - recordType can't be used to filter
    # HostRecord queries, so "HostRecord" deliberately has no entry here and
    # a -t host-style query still returns every record type unfiltered,
    # same as before this fix.
}
# GenericRecord is v1's wrapper for "everything else" (A, AAAA, NS, ...) -
# unlike the dedicated types above, its recordType is the actual DNS
# mnemonic, not a fixed value, so a single recordType:'X' filter can't
# represent it. CONFIRMED live (debug_rrtypes.py): A and NS both show up as
# type=GenericRecord. AAAA isn't confirmed live but follows the exact same
# naming pattern every other confirmed type did, so it's included too.
# zone_rr_query.py/dump_rr.py only ever request GenericRecord for these
# three subtypes (their generic_subtype logic) plus one bare "-t generic"
# catch-all for any other/rarer recordType, which this filter does NOT
# cover (that call would come back empty rather than unfiltered) - extend
# this tuple if a script actually needs one of those less-common types.
#
# KNOWN SERVER QUIRK (CONFIRMED live via dump_rr.py -t ns): this
# `recordType:in(...)` filter correctly excludes CNAME/SRV/NAPTR/TXT/HINFO,
# but HostRecord entries (recordType is entirely absent, not just a
# non-matching value - see the "HostRecord" comment above) still come back
# too - the server treats a record with no 'recordType' field at all as
# exempt from any recordType-based filter rather than excluded by it, for
# both plain equality and `in()`. No other confirmed-filterable field
# distinguishes HostRecord from GenericRecord, so this can't be fixed with
# a better server-side filter. getEntities()/getEntitiesByName() work
# around it for the GenericRecord case specifically by fetching everything
# the server filter lets through (via _fetch_all_raw()) and dropping
# anything whose real top-level 'type' isn't "GenericRecord" client-side,
# then paginating the fully-correct list themselves - see the comments
# there for why a naive client-side filter can't just be layered on top of
# the normal single-page call.
GENERIC_RECORD_SUBTYPES = ("A", "AAAA", "NS")

# CONFIRMED live from cname_add.py's InvalidResourceType 400 - the server
# echoed its full "acceptedTypes" list for the 'linkedRecord.type'/'type'
# fields of a resourceRecords POST. This is the authoritative set of real
# v2 resource-record type enum values (used by _resolve_linked_record() to
# restrict its lookup to actual records, never a Zone or other non-record
# entity that might share the same absoluteName). Notably this does NOT
# include "CNAMERecord" - the real type for a CNAME is "AliasRecord" - and
# includes a few types this shim hadn't encountered yet (HTTPSRecord,
# SVCBRecord, URIRecord).
#
# CONFIRMED live (2026-09-21, cname_add.py -i pointed at a plain "A" record
# added via a_add.py/addGenericRecord - top-level type "GenericRecord"):
# despite being in that same acceptedTypes list, "GenericRecord" is NOT
# actually a valid linkedRecord.type - the POST still 400s with
# InvalidResourceType. Re-pointing the same command at a real HostRecord
# (added via host_add.py) instead worked immediately with no other change.
# So a CNAME/SRV/Alias's target must be a HostRecord (or one of the other
# types below) - it can NOT be a plain address/generic-type record added
# via a_add.py/generic_add.py/ns_add.py/etc. Removed from this list so
# _resolve_linked_record() skips a GenericRecord match and keeps looking
# (or reports "target record must already exist" instead of a confusing
# server-side InvalidResourceType) rather than resolving to a type the
# server will just reject anyway.
LINKABLE_RECORD_TYPES = (
    "AliasRecord", "ExternalHostRecord", "HINFORecord",
    "HTTPSRecord", "HostRecord", "MXRecord", "NAPTRRecord", "SRVRecord",
    "SVCBRecord", "TXTRecord", "URIRecord",
)

# ----------------------------------------------------------------------------
# CONFIRMED from a live 400 response ("InvalidFilterEnumValue") on this v26.1
# server: the v2 API's actual "type" enum values do NOT always match the v1
# type strings scripts pass around (e.g. v1's "IP4Block" vs v2's "IPv4Block").
# TYPE_LINK_KEY above maps a v1 type string to the right *collection link
# key* (fine to keep loose); this table maps a v1 type string to the exact
# v2 "type" enum value the server expects whenever that string is sent
# in a `filter=type:...` query or as a request body's "type" field. Values
# not listed here are passed through unchanged (already correct, e.g.
# HostRecord/AliasRecord/Zone/Configuration/View/User/Server/MACPool/...).
V1_TYPE_TO_V2_ENUM = {
    "IP4Block": "IPv4Block", "IP6Block": "IPv6Block",
    "IP4Network": "IPv4Network", "IP6Network": "IPv6Network",
    "IP4Address": "IPv4Address", "IP6Address": "IPv6Address",
    "DHCP4Range": "IPv4DHCPRange", "DHCP6Range": "IPv6DHCPRange",
    "DHCPRange": "IPv4DHCPRange", "Range": "IPv4DHCPRange",
    # VERIFY: not confirmed against this server - "ClientClass" isn't a v2
    # enum value at all; DHCPv4ClientClass/DHCPv4Subclass are the closest
    # matches in the accepted-values list but haven't been tested live.
    "ClientClass": "DHCPv4ClientClass",
}


def _v2_type_enum(ttype):
    """Translate a v1-style type string to the real v2 API 'type' enum
    value (see V1_TYPE_TO_V2_ENUM above), passing it through unchanged if
    there's no known difference."""
    return V1_TYPE_TO_V2_ENUM.get(ttype, ttype)


# ----------------------------------------------------------------------------
# CONFIRMED from a live debug dump (debug_zone.py): a v1 property name can
# differ from the real v2 field name entirely (not just the entity 'type'
# handled above). v1's Zone had a 'deployable' property (lower-case
# 'true'/'false' string, per zone_query.py/zone_update.py's
# `properties['deployable'] == 'true'` checks); the real v2 Zone field is
# 'deploymentEnabled', a genuine JSON boolean. This table maps the v1-facing
# property name -> the real v2 field name, for any entity type - extend it
# as more of these turn up (the same generic _v2_to_v1()/update()/addZone()
# code path is shared by every entity, so a new alias here fixes every
# script that reads/writes that property, not just one).
V1_PROP_FIELD_ALIAS = {
    "deployable": "deploymentEnabled",
    # NAPTRRecord: v1 scripts (zone_rr_query.py, addNAPTRRecord()) use
    # 'regexp', but the real v2 NAPTRRecord field is 'regularExpression'
    # (confirmed live via debug_naptr.py - order/preference/service/
    # replacement/flags all matched their v1 names as-is, only this one
    # differed).
    "regexp": "regularExpression",
    # TXTRecord: v1 scripts (zone_rr_query.py, addTXTRecord()) use 'txt',
    # but the real v2 TXTRecord field is 'text' (confirmed live via
    # debug_txt.py).
    "txt": "text",
    # SRVRecord/AliasRecord/MXRecord: v1 scripts (zone_rr_query.py,
    # addSRVRecord()/addAliasRecord()) use 'linkedRecordName', but the real
    # v2 field is 'linkedRecord' - a nested resource-record object, not a
    # plain string (confirmed live via debug_srv.py). The value-extraction
    # from that nested object happens in _v2_to_v1() itself.
    "linkedRecordName": "linkedRecord",
    # HostRecord: 'reverseRecord' (the PTR flag) is already the same field
    # name in both v1 and v2, but v2 returns a real JSON boolean (True/False)
    # while v1 scripts (zone_rr_query.py: `properties['reverseRecord']`)
    # expect the lower-case 'true'/'false' string v1 used - self-mapped here
    # purely so it goes through the boolean-coercion branch below.
    "reverseRecord": "reverseRecord",
    # NetworkInterface (see TYPE_LINK_KEY's 'NetworkServerInterface' entry):
    # v1 scripts (server_query.py, dnsRole_add.py, dns_forwarding_add.py,
    # etc.) read 'servicesIPv4Address'/'defaultInterfaceAddress' off the
    # interface entity; the real v2 fields are 'servicesIpv4Address' (note
    # casing) and 'managementAddress' (confirmed live via debug_server.py).
    "servicesIPv4Address": "servicesIpv4Address",
    "defaultInterfaceAddress": "managementAddress",
    # DHCP4Range/DHCP6Range (real v2 type IPv4DHCPRange/IPv6DHCPRange):
    # v1's 'SplitStaticAddresses' boolean property (dhcp4range_query.py)
    # is the real v2 field 'splitAroundStaticAddresses' (confirmed live via
    # debug_dhcp4range.py). 'start'/'end' and 'excludeDHCPRange' are NOT
    # simple 1:1 field renames (v2 has one combined 'range' string and a
    # list-shaped 'exclusionRanges' instead) - those are synthesized by
    # custom code in _v2_to_v1() below, not this generic alias table.
    "SplitStaticAddresses": "splitAroundStaticAddresses",
}
# v1-facing property names (the LEFT side of V1_PROP_FIELD_ALIAS) that are
# booleans encoded as v1's lower-case 'true'/'false' strings - these get
# coerced to/from a real JSON boolean wherever they're read or written.
V1_BOOLEAN_PROP_KEYS = {"deployable", "reverseRecord", "SplitStaticAddresses"}


def _v1_props_for_write(properties):
    """Parse a v1 pipe-delimited properties string (as built by a script's
    joinProp()) into a dict ready to merge into a v2 request body: any
    property name in V1_PROP_FIELD_ALIAS gets renamed to its real v2 field
    name, and any property in V1_BOOLEAN_PROP_KEYS gets coerced from v1's
    'true'/'false' string convention to a real JSON boolean. Use this
    instead of the raw _v1_props_to_dict() wherever a v1 properties string
    is about to be sent to the v2 API (addZone(), update(), etc.)."""
    d = _v1_props_to_dict(properties)
    out = {}
    for k, v in d.items():
        if k in V1_BOOLEAN_PROP_KEYS:
            v = str(v).strip().lower() == "true"
        elif v == "None":
            # CONFIRMED live (a_update.py's InvalidTtlValue): a real JSON
            # null gets stringified into the literal text "None" when
            # _dict_to_v1_props() encodes it for splitProp() (matching v1's
            # own convention of scripts checking e.g.
            # `properties['ttl'] == 'None'`). Decoded back here on the
            # write path, that literal string "None" is not a valid value
            # for most v2 fields - ttl in particular rejects it outright
            # with InvalidTtlValue rather than treating it as "leave
            # unset". Skip the field entirely instead of sending the string
            # "None" - same "omit rather than guess" convention as
            # _normalize_ttl()'s handling of v1's -1 sentinel.
            continue
        out[V1_PROP_FIELD_ALIAS.get(k, k)] = v
    return out


def _v1_props_to_dict(properties):
    """Same pipe-delimited format v1's splitProp() parsed: 'k=v|k2=v2|' -> {k:v,...}."""
    if not properties:
        return {}
    outlist = []
    for inl in [a.split("|") for a in properties.split(r"\|")]:
        if outlist:
            outlist[-1] += "|"
            if inl:
                outlist[-1] += inl.pop(0)
        for i in inl:
            outlist.append(i)
    d = [a.split("=", 1) for a in outlist if a]
    return dict(d)


def _dict_to_v1_props(d):
    """Inverse of _v1_props_to_dict() - identical format to v1's joinProp()."""
    return "|".join([
        "%s=%s" % (k, str(v).replace("\\", "\\\\").replace("|", "\\|"))
        for k, v in d.items()
    ]) + "|"


def _normalize_ttl(ttl):
    """v1 scripts pass ttl=-1 (as int or str) to mean "no explicit TTL -
    inherit the zone/network default". v2's 'ttl' field must be an integer
    in 0..2147483647 and 400s ("ValueOutsideRange") on a negative value, so
    -1 has to be dropped from the request body entirely (letting the server
    apply its own default) rather than sent through as-is. Returns an int
    for any other value, or None when the field should be omitted."""
    if ttl is None:
        return None
    try:
        ttl_int = int(ttl)
    except (TypeError, ValueError):
        return None
    if ttl_int < 0:
        return None
    return ttl_int


def _name_field(rel_name):
    """Returns the body-level 'name' field for a normal (non-apex) record,
    or {} (no 'name' key at all) for a zone-apex ("-k"/same-as-zone)
    record. SUPERSEDES an earlier, WRONG conclusion that a blank-string
    'name' was how v1's "same as zone" concept mapped onto v2 (based on
    debug_txt.py appearing to show a TXT record accepted with 'name': '') -
    that also seemed to make AliasRecord/CNAME's blank-name 400 look like a
    deliberate DNS-rule rejection, which was ALSO wrong. CONFIRMED WORKING
    instead (per an independently-built v2 shim from another engineer,
    BAM-jerry.py, shared live 2026-09-21): apex is signaled purely via the
    'x-bcn-same-as-zone: true' REQUEST HEADER (see _same_as_zone_headers()
    below) - 'name' must be entirely ABSENT from the body in that case,
    for every record type alike. (Earlier attempts at a magic stand-in
    body value - blank string, null, omitted, "@", the zone's own name -
    were all WRONG: each either 400'd or was accepted but produced a wrong
    literal record like "@"/"<zone>.<zone>" instead of a true zone-apex
    record; see debug_genericrecord_apex*.py.)"""
    return {} if rel_name == "" else {"name": rel_name}


def _same_as_zone_headers(rel_name):
    """The request headers to pair with _name_field(rel_name) above - see
    its docstring for how this was confirmed. Returns None for a normal
    (non-apex) record."""
    return {"x-bcn-same-as-zone": "true"} if rel_name == "" else None


class BAM():

    req_timeout = 3     # class var, can be updated by BAM.req_timeout. Once it is changed, all instant will change
    bam_debug = False    # debug flag

    def __init__(self, BAM_URL, req_timeout):
        # BAM_URL arrives as the v1-style base every script already builds,
        # e.g. "http://10.1.1.113/Services/REST/v1/". Translate it to the
        # v2 API's host base so every existing caller keeps working
        # unchanged - they never see this URL directly. Assigned through the
        # BAM_URL property below (not a plain attribute) so that scripts
        # which reuse a single long-lived BAM() instance across recursive
        # calls and reassign `bam.BAM_URL = ...` after construction instead
        # of creating a new BAM() (CONFIRMED live in dump_rr.py, which does
        # `bam = BAM.BAM("", 3)` once at import time then later
        # `bam.BAM_URL = BAM_URL; bam.login(...)`) still get api_base
        # recomputed - v1 read self.BAM_URL fresh on every request, so this
        # pattern worked unchanged there; our api_base is a derived value
        # that has to be kept in sync the same way.
        self.BAM_URL = BAM_URL
        self.token = ""
        self.url = ""
        self.param = {}
        self.header = {}
        self.data = {}      # data is http body
        self.req_timeout = req_timeout
        self.session = requests.Session()
        self.session.verify = False
        # ------------------------------------------------------------
        # PERFORMANCE: per-instance caches. v1 could resolve most things
        # (get/update/delete by a bare numeric id) in a single RPC call;
        # v2's hypermedia model means the same operation often needs a
        # "resolve by id" lookup first, then a follow-up request on
        # whatever _links it returns. Scripts frequently re-resolve the
        # same id multiple times in one run (e.g. access_rights.py calls
        # getConfiguration(ent['id']) - which walks up via getParent(),
        # itself calling _get_by_id() - once per candidate entity found
        # during a search). Caching for the lifetime of this BAM instance
        # (i.e. one script invocation) avoids repeating those lookups.
        # Entries are invalidated in update()/delete() so a script that
        # modifies then re-reads the same id within one run still sees
        # fresh data.
        self._entity_cache = {}       # str(id) -> raw v2 JSON (or None)
        self._config_list_cache = None  # list of raw Configuration JSON
        self._range_search_cache = {}   # (keyword, link_keys) -> [raw JSON]

    # ------------------------------------------------------------------
    # BAM_URL is a property (not a plain attribute) so that reassigning it
    # after construction - `bam.BAM_URL = "http://host/Services/REST/v1/"` -
    # recomputes api_base too. See the __init__ comment above for why this
    # matters (dump_rr.py's reused-instance pattern).
    # ------------------------------------------------------------------
    @property
    def BAM_URL(self):
        return self._bam_url

    @BAM_URL.setter
    def BAM_URL(self, value):
        self._bam_url = value
        api_base = re.sub(r"/Services/REST/v1/?$", "", value or "")
        if api_base.endswith("/"):
            api_base = api_base[:-1]
        self.api_base = api_base

    # ------------------------------------------------------------------
    # internal v2 request helpers
    # ------------------------------------------------------------------
    def _url(self, path):
        """path is either a full v2 href as returned in a resource's _links
        (e.g. '/api/v2/configurations/100881/views') or one we build
        ourselves the same way (always starting with /api/v2)."""
        return self.api_base + path

    def _raise_for_error(self, response, method=None, path=None):
        # CONFIRMED live across every error surfaced so far: this server's
        # v2 errors come back as a flat JSON object - {"status":...,
        # "reason":..., "code":..., "message":..., "detail":...} - not the
        # {"errors":[{"title","detail"}]} shape some other v2 deployments
        # use. Format that as "[code] message (detail)", per explicit
        # request, instead of dumping "[METHOD path] {raw json blob}" -
        # much easier to read and to relay back when reporting an error.
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("errors"):
            first = body["errors"][0]
            code = first.get("code") or first.get("title") or "Error"
            msg = first.get("detail") or first.get("title") or json.dumps(body)
            raise ValueError("[%s] %s" % (code, msg))
        if isinstance(body, dict) and (body.get("code") or body.get("message")):
            code = body.get("code", "Error")
            msg = body.get("message") or json.dumps(body)
            detail = body.get("detail")
            if detail and detail != msg:
                msg = "%s (%s)" % (msg, detail)
            raise ValueError("[%s] %s" % (code, msg))
        # Fallback (body isn't the JSON error shape above - e.g. an HTML
        # error page, or no body at all): keep the old method/path-prefixed
        # form so there's still SOME diagnostic context in that rarer case.
        msg = json.dumps(body) if body is not None else response.text
        if method and path:
            msg = "[%s %s] %s" % (method, path, msg)
        raise ValueError(msg)

    def _req(self, method, path, **kwargs):
        url = self._url(path)
        kwargs.setdefault("timeout", self.req_timeout)
        headers = kwargs.pop("headers", None) or self.header
        response = self.session.request(method, url, headers=headers, verify=False, **kwargs)
        if not response.ok:
            self._raise_for_error(response, method=method, path=path)
        return response

    def _get(self, path, **params):
        params = {k: v for k, v in params.items() if v is not None}
        return self._req("GET", path, params=params).json()

    def _post(self, path, body, headers=None):
        if headers:
            merged = dict(self.header)
            merged.update(headers)
            return self._req("POST", path, json=body, headers=merged)
        return self._req("POST", path, json=body)

    def _put(self, path, body):
        return self._req("PUT", path, json=body)

    def _patch(self, path, body):
        return self._req("PATCH", path, json=body)

    def _delete(self, path):
        return self._req("DELETE", path)

    def _get_by_id(self, entity_id, use_cache=True):
        """Resolve any resource by its bare numeric id, regardless of type -
        the v2 equivalent of v1's implicit "the API knows every object by
        id" behavior. PERFORMANCE: cached per BAM instance (see __init__) -
        this is the single most-repeated lookup in the whole shim (every
        getParent/getConfiguration/_resolve_parent_collection call goes
        through it), so avoiding a repeat round trip for the same id within
        one script run matters a lot. Pass use_cache=False to force a fresh
        read (e.g. right after a write you know changed this same id)."""
        if entity_id is None or str(entity_id) in ("0", ""):
            return None
        key = str(entity_id)
        if use_cache and key in self._entity_cache:
            return self._entity_cache[key]
        try:
            result = self._get("/api/v2", filter="id:%s" % entity_id)
        except ValueError:
            return None
        data = result.get("data", [])
        ent = data[0] if data else None
        self._entity_cache[key] = ent
        return ent

    def _invalidate_entity_cache(self, entity_id):
        """Drop a cached _get_by_id() entry - call after any write that
        changes an entity's own fields, so a script that reads-modifies-reads
        the same id within one run still sees fresh data."""
        self._entity_cache.pop(str(entity_id), None)

    def _resolve_linked_record(self, absoluteName):
        """Resolve a resource record by its absoluteName to the
        {'id':..., 'type':...} reference v2 wants for a 'linkedRecord'
        field (addSRVRecord()/addAliasRecord()). CONFIRMED live
        (cname_add.py's MissingRequiredField: "'linkedRecord.type' is a
        required field"): v1's addAliasRecord()/addSRVRecord() only ever
        took a plain target-name string (v1 apparently resolved the type
        itself server-side), so this shim has to look the target up to
        learn its real type before it can build a valid linkedRecord
        object. Uses the same root '/api/v2?filter=...' resolution trick as
        _get_by_id() (confirmed there for 'id:...' - 'absoluteName:...' is
        confirmed too, but needed a type restriction added afterward: a
        Zone entity also has its own 'absoluteName' matching the zone name,
        so an unrestricted search can match the zone itself instead of a
        record within it - CONFIRMED live, InvalidResourceType named the
        zone's own type as invalid for linkedRecord). Restricted to
        LINKABLE_RECORD_TYPES (the server's own accepted-types list from
        that same error) rather than RESOURCE_RECORD_TYPES - the latter
        includes "CNAMERecord", which that list proves is NOT a real v2
        enum value (the real one is "AliasRecord"), so including it here
        would risk an InvalidFilterEnumValue 400 instead."""
        record_types = ",".join("'%s'" % t for t in LINKABLE_RECORD_TYPES)
        result = self._get("/api/v2", filter="absoluteName:'%s' and type:in(%s)" % (absoluteName, record_types))
        data = result.get("data", [])
        if not data:
            raise ValueError(
                "BAM v2 shim: could not resolve linked record '%s' - the "
                "target record must already exist" % absoluteName)
        target = data[0]
        return {"id": target["id"], "type": target["type"]}

    def _link_key(self, ttype):
        key = TYPE_LINK_KEY.get(ttype)
        if not key:
            raise ValueError(
                "BAM v2 shim: unmapped v1 type '%s' - add it to TYPE_LINK_KEY "
                "in BAM.py (see the bluecat-integrity-api skill's migration "
                "table for the right v2 collection name)" % ttype)
        return key

    def _resolve_parent_collection(self, parentId, ttype):
        """Given a v1 (parentId, type) pair, return the v2 collection URL to
        list/create children of that type under that parent."""
        link_key = self._link_key(ttype)
        if parentId is None or str(parentId) == "0":
            # v1 used parentId=0 to mean "root". A handful of v2 collections
            # (not just Configuration) genuinely live at /api/v2/<name>
            # regardless of any parent - e.g. v1 scripts call
            # getAllEntities(0, "User")/("UserGroup") to list every user or
            # group account, which isn't scoped to a Configuration in v1
            # either. CONFIRMED for "configurations"; the rest are
            # best-effort (adjust if one 404s).
            if link_key in ("configurations", "users", "userGroups", "servers", "tagGroups"):
                return "/api/v2/" + link_key
            raise ValueError(
                "BAM v2 shim: parentId=0 is only valid when type is "
                "Configuration/User/UserGroup/Server/TagGroup (got type "
                "mapped to '%s')" % link_key)
        parent = self._get_by_id(parentId)
        if not parent:
            raise ValueError("Parent entity id %s not found" % parentId)
        links = parent.get("_links", {})
        if link_key not in links:
            raise ValueError(
                "BAM v2 shim: parent id %s (%s) has no '%s' sub-collection" %
                (parentId, parent.get("type"), link_key))
        return links[link_key]["href"]

    def _v2_to_v1(self, obj):
        """Reshape a v2 JSON resource into the {id, name, type, properties}
        shape the existing scripts expect. Every field besides id/name/type
        is encoded into the same pipe-delimited 'properties' string v1 used,
        so splitProp()/joinProp() keep working unchanged. '_links' is kept
        too (scripts ignore unknown dict keys) so this module's own
        delete()/update() can resolve the resource's v2 endpoint later."""
        if obj is None:
            return {"id": 0, "name": None, "type": None, "properties": None}
        # NOTE: 'type' is deliberately kept in `extra` (and therefore in the
        # encoded properties string) as well as at the top level. In v1, a
        # GenericRecord's *actual* DNS record type (e.g. "A") lived inside
        # its properties string ("type=A|..."), not in the entity's
        # top-level 'type' field (which was the generic wrapper type). v2
        # puts the real type directly on the resource's top-level 'type'
        # field instead. Scripts written against v1 do
        # `properties = bam.splitProp(ent); if properties['type'] == "A":`
        # so 'type' has to be recoverable from splitProp() too, regardless
        # of which API version actually stores it there.
        extra = {k: v for k, v in obj.items() if k not in ("id", "name", "_links")}
        if "recordType" in obj:
            # v1 exposed a DNS resource record's *actual* type (A, CNAME,
            # MX, ...) under properties['type']; this server's v2 API wraps
            # generic records under the top-level type "GenericRecord" and
            # puts the real type in a separate 'recordType' field instead.
            # Override 'type' in the encoded properties with that real
            # value so `properties['type']=="A"`-style checks in the
            # existing scripts (a_query.py, generic_query.py, etc.) work
            # exactly like they did against v1.
            extra["type"] = obj["recordType"]
        # CONFIRMED (debug_zone.py): some v1 property names don't match the
        # real v2 field name at all (Zone's 'deployable' vs v2's real
        # 'deploymentEnabled') - add the v1-facing alias alongside the real
        # v2 key (kept too, harmless) so `properties['deployable']`-style
        # checks in existing scripts keep working, with the exact 'true'/
        # 'false' string casing v1 used for booleans.
        for v1_key, v2_key in V1_PROP_FIELD_ALIAS.items():
            if v1_key in V1_BOOLEAN_PROP_KEYS:
                # CONFIRMED: some entities returned alongside regular Zones
                # in a "list zones under this view" query (special zone
                # subtypes like ExternalHostsZone/InternalRootZone/etc.)
                # don't carry 'deploymentEnabled' at all, unlike a directly
                # name-filtered lookup of an ordinary Zone (which does) -
                # v1 apparently always exposed 'deployable' regardless, so
                # default it to 'false' rather than omitting the key, or
                # scripts that iterate a whole zone list (zone_query.py -a)
                # KeyError on the entries that lack it.
                val = extra.get(v2_key)
                extra[v1_key] = "true" if (val is True or str(val).strip().lower() == "true") else "false"
            elif v2_key in extra:
                val = extra[v2_key]
                # CONFIRMED (debug_srv.py): SRVRecord's real v2 field for its
                # target is 'linkedRecord', a nested resource-record object
                # ({id, type, name, absoluteName, _links}), not a plain
                # string like v1's 'linkedRecordName'. Same generic reshaper
                # is used for AliasRecord/MXRecord, which almost certainly
                # carry the same nested-object shape - extract the target's
                # absoluteName (falling back to its bare name) so
                # `properties['linkedRecordName']`-style checks keep getting
                # a plain string like v1 did.
                if isinstance(val, dict):
                    val = val.get("absoluteName") or val.get("name")
                extra[v1_key] = val
        # CONFIRMED (zone_query_all.py, same live server): those same
        # non-authoritative zone subtypes that omit 'deploymentEnabled' also
        # omit 'absoluteName' - v1 apparently always exposed it (scripts do
        # properties['absoluteName'] unconditionally when iterating a zone
        # list), so fall back to the plain 'name' rather than leaving the
        # key out entirely.
        if "absoluteName" not in extra and obj.get("name") is not None:
            extra["absoluteName"] = obj["name"]
        # CONFIRMED live (debug_server.py): the v1 Server entity carried a
        # 'fullHostName' property (plus 'defaultInterfaceAddress'/
        # 'servicesIPv4Address') that simply don't exist on the v2 Server
        # resource at all - they live on its NetworkInterface sub-resource
        # instead (reached via the server's own '_links.interfaces'
        # collection). Synthesize the v1-facing properties from the
        # server's first interface so `properties['fullHostName']`-style
        # code (deploy_server.py, deploy_status.py, server_query.py,
        # server_role.py, dnsRole_add.py, dnsRole_delete.py,
        # dns_forwarding_add.py, dns_forwardingPolicy_add.py) keeps working
        # unchanged. A server with no interfaces at all simply won't get
        # these keys (matches the "if 'fullHostName' in properties:" guard
        # some of those scripts already use for that case).
        if obj.get("type") == "Server" and "interfaces" in obj.get("_links", {}):
            try:
                ifaces = self._get(obj["_links"]["interfaces"]["href"]).get("data", [])
            except Exception:
                ifaces = []
            if ifaces:
                primary = ifaces[0]
                if primary.get("name"):
                    extra["fullHostName"] = primary["name"]
                if primary.get("servicesIpv4Address"):
                    extra["servicesIPv4Address"] = primary["servicesIpv4Address"]
                if primary.get("managementAddress"):
                    extra["defaultInterfaceAddress"] = primary["managementAddress"]
        # CONFIRMED live (debug_dhcp4range.py): DHCP4Range/DHCP6Range (real
        # v2 type IPv4DHCPRange/IPv6DHCPRange) has one combined 'range'
        # field ("<start> - <end>", with spaces around the dash) instead of
        # v1's separate 'start'/'end' properties (dhcp4range_query.py does
        # properties['start']/['end'] and got a KeyError) - split it back
        # into the two v1-facing keys. Also v1's 'excludeDHCPRange' was a
        # comma-separated "start-end,start2-end2," string
        # (dhcp4range_query.py's own comment shows this format); the real
        # v2 field 'exclusionRanges' is a list instead - VERIFY: only ever
        # observed empty live so far, so the per-item shape (assumed to
        # also be a dict with its own "<start> - <end>" 'range' string,
        # mirroring the parent range) is a best-effort guess.
        if obj.get("type") in ("IPv4DHCPRange", "IPv6DHCPRange"):
            raw_range = extra.get("range")
            if isinstance(raw_range, str) and " - " in raw_range:
                start_s, end_s = raw_range.split(" - ", 1)
                extra["start"] = start_s.strip()
                extra["end"] = end_s.strip()
            exclusions = extra.get("exclusionRanges")
            if isinstance(exclusions, list):
                pieces = []
                for item in exclusions:
                    if isinstance(item, dict) and isinstance(item.get("range"), str):
                        pieces.append(item["range"].replace(" - ", "-"))
                    elif isinstance(item, str):
                        pieces.append(item.replace(" - ", "-"))
                extra["excludeDHCPRange"] = (",".join(pieces) + ",") if pieces else ""
        # CONFIRMED (zone_rr_query.py live output): HostRecord's 'addresses'
        # field is a list of nested IPv4Address/IPv6Address objects, not the
        # flat comma-separated IP string v1 exposed under the same property
        # name (script does `properties['addresses']` expecting something
        # printable as "IP:10.1.1.133"). Collapse to a comma-separated list
        # of address strings to match v1's format.
        if isinstance(extra.get("addresses"), list):
            addr_strs = [
                a.get("address") for a in extra["addresses"]
                if isinstance(a, dict) and a.get("address")
            ]
            extra["addresses"] = ",".join(addr_strs)
        return {
            "id": obj.get("id", 0),
            # CONFIRMED live (zone_rr_query.py: a "same as zone" record
            # printed "Name:None" instead of v1's "(Same as Zone)"): v2
            # returns a real JSON null for a record's name when it's at the
            # zone apex, but v1 always used an empty string there (scripts
            # do `if item['name'] == '':`) - coerce None to "" to match.
            "name": obj.get("name") or "",
            "type": obj.get("type"),
            "properties": _dict_to_v1_props(extra) if extra else "",
            "_links": obj.get("_links", {}),
        }

    def _zone_and_relname(self, viewId, absoluteName, properties=""):
        """v1's record-add methods take a view id plus a full absoluteName
        and let the server figure out which zone it belongs to. v2 requires
        the specific zone's id as the parent collection. Scripts in this
        project already pass a 'parentZoneName=...' hint inside 'properties'
        (see host_add.py/a_add.py) precisely so this split can be done
        reliably - use that hint first, then fall back to trying
        progressively shorter dotted suffixes (longest zone match first)."""
        props = _v1_props_to_dict(properties)
        hint = props.get("parentZoneName")
        if hint:
            zone_ent = self.find_zone(viewId, hint)
            if zone_ent.get("id"):
                if absoluteName in (hint, "." + hint):
                    return zone_ent["id"], ""
                suffix = "." + hint
                if absoluteName.endswith(suffix):
                    return zone_ent["id"], absoluteName[: -len(suffix)]
        # fall back: try progressively shorter dotted suffixes as the zone
        # name, longest match first (mirrors how the v1 server resolved a
        # bare FQDN when no hint was given)
        labels = absoluteName.lstrip(".").split(".")
        for i in range(len(labels) - 1):
            candidate_zone = ".".join(labels[i + 1:])
            if not candidate_zone:
                continue
            zone_ent = self.find_zone(viewId, candidate_zone)
            if zone_ent.get("id"):
                return zone_ent["id"], ".".join(labels[:i + 1])
        raise ValueError("Could not resolve a zone for '%s' under view %s" % (absoluteName, viewId))

    # ------------------------------------------------------------------
    # auth
    # ------------------------------------------------------------------
    def login(self, username, password):
        url = self._url("/api/v2/sessions")
        response = self.session.post(url, json={"username": username, "password": password},
                                      verify=False, timeout=self.req_timeout)
        if response.ok:
            data = response.json()
            self.token = "Basic " + data["basicAuthenticationCredentials"]
            self.header = {
                "Authorization": self.token,
                "Content-Type": "application/json",
                "Accept": "application/hal+json",
            }
            return response
        self._raise_for_error(response)

    def logout(self):
        url = self._url("/api/v2/sessions/current")
        response = self.session.patch(url, json={"state": "LOGGED_OUT"}, headers=self.header,
                                       verify=False, timeout=self.req_timeout)
        return response

    # -----------------------------------------------------------------------------
    # addUser() / updateUserPassword()
    def addUser(self, username, password, properties):
        body = {"type": "User", "name": username, "password": password}
        body.update(_v1_props_to_dict(properties))
        created = self._post("/api/v2/users", body).json()
        return created.get("id", 0)

    def updateUserPassword(self, userId, newPassword, options):
        self._req("PATCH", "/api/v2/users/%s" % userId, json={"password": newPassword})
        return

    # -----------------------------------------------------------------------------
    # getAll() - generic generator wrapper, unchanged from v1 (pure pagination
    # logic layered on top of the methods below, no API-version dependency).
    def getAll(self, fn, *args):
        args = list(args)
        args.append(0)
        args.append(100)
        while True:
            results = fn(*args)
            if not len(results):
                return
            for result in results:
                yield result
            args[-2] += len(results)

    def getAllEntities(self, parentId, ttype):
        return self.getAll(self.getEntities, parentId, ttype)

    def getAllLinkedEntities(self, Id, ttype):
        return self.getAll(self.getLinkedEntities, Id, ttype)

    def getAllEntitiesByName(self, parentId, name, ttype):
        return self.getAll(self.getEntitiesByName, parentId, name, ttype)

    def getAllAccessRightsForUser(self, userId):
        return self.getAll(self.getAccessRightsForUser, userId)

    def searchAllByCategory(self, parentId, category):
        return self.getAll(self.searchByCategory, parentId, category)

    def searchAllByObjectTypes(self, parentId, ttype):
        return self.getAll(self.searchByObjectTypes, parentId, ttype)

    def getAllEntitiesByNameUsingOptions(self, name, ttype, options):
        return self.getAll(self.getEntitiesByNameUsingOptions, name, ttype, options)

    def getAllAliasesByHint(self, options):
        return self.getAll(self.getAliasesByHint, options)

    def getAllIP4NetworksByHint(self, containerId, options):
        return self.getAll(self.getIP4NetworksByHint, containerId, options)

    def getAllAccessRightsForEntity(self, entityId):
        return self.getAll(self.getAccessRightsForEntity, entityId)

    def customSearchAll(self, filters, ttype, options):
        return self.getAll(self.customSearch, filters, ttype, options)

    def searchAllResponsePolicyItems(self, keyword, scope, properties):
        return self.getAll(self.searchResponsePolicyItems, keyword, scope, properties)

    # -----------------------------------------------------------------------------
    def getParent(self, entityId):
        ent = self._get_by_id(entityId)
        if not ent:
            return {"id": 0}
        # Configurations are top-level in v1's model; v2's Configuration
        # resource has an "up" link to a root pseudo-object (id 1) that has
        # no real parent semantics - treat both cases as v1's "no parent".
        if ent.get("type") == "Configuration":
            return {"id": 0}
        up = ent.get("_links", {}).get("up", {}).get("href")
        if not up:
            return {"id": 0}
        parent = self._get(up)
        if not parent or not parent.get("type"):
            return {"id": 0}
        return self._v2_to_v1(parent)

    # -----------------------------------------------------------------------------
    def getEntityByName(self, parentId, name, type, debug=False):
        collection = self._resolve_parent_collection(parentId, type)
        result = self._get(collection, filter="name:'%s'" % name)
        data = result.get("data", [])
        v1 = self._v2_to_v1(data[0] if data else None)
        if debug:
            print('\ndebug: --- bam.getEntityByName() ---')
            print(v1)
            print('--- End of bam.getEntityByName() ---\n')
        return v1

    # v1 types that can't be reliably isolated with a server-side
    # recordType filter alone (see getEntities()'s handling of these) and
    # so need the fetch-everything/filter-by-real-type/self-paginate
    # treatment instead: HostRecord has no recordType at all (CONFIRMED via
    # debug_rrtypes.py - always None), and GenericRecord's recordType:in(A,
    # AAAA,NS) filter doesn't exclude those same recordType-less HostRecord
    # entries (CONFIRMED live via dump_rr.py -t ns).
    FETCH_ALL_RR_TYPES = {"GenericRecord", "HostRecord"}

    @staticmethod
    def _rr_type_filter(type):
        """Return the recordType-based filter clause (no leading/trailing
        'and') needed to restrict a resourceRecords query to just the given
        v1 type, or None if no such filter is known/possible (see
        V1_RRTYPE_TO_RECORDTYPE_FILTER/GENERIC_RECORD_SUBTYPES above)."""
        if type in V1_RRTYPE_TO_RECORDTYPE_FILTER:
            return "recordType:'%s'" % V1_RRTYPE_TO_RECORDTYPE_FILTER[type]
        # CONFIRMED live (generic_delete.py -t spf -r spf1: "No record
        # found!" even though the record existed) - a
        # 'recordType:in(A,AAAA,NS)' narrowing here silently excludes any
        # OTHER generic recordType (SPF, MX, HINFO, ...) before
        # getEntitiesByName()'s own client-side `properties['type']==rrtype`
        # check ever runs. That narrowing was only ever safe for dump_rr.py/
        # zone_rr_query.py's specific A/AAAA/NS-subtype callers (which
        # re-verify the exact subtype client-side anyway, so they're
        # unaffected by this removal) - it was never safe for
        # generic_add.py/generic_delete.py/generic_query.py/
        # generic_update.py, which pass type="GenericRecord" for ANY '-t
        # rrtype' value and rely entirely on getting the full candidate set
        # back to filter themselves. Deliberately return None (no
        # server-side recordType filter at all) instead - correctness for
        # arbitrary generic types matters more than the fetch-size
        # optimization, and _fetch_all_raw()'s existing top-level
        # 'type'=="GenericRecord" check already keeps other record kinds
        # (TXT/SRV/NAPTR/CNAME/Host) out.
        return None

    def _fetch_all_raw(self, collection, filt, page_size=1000):
        """Fetch every raw v2 item matching `filt` from `collection`,
        looping over as many server-side pages as it takes. Used only where
        a further CLIENT-side filter has to be layered on top of the
        server-side one (see getEntities()'s GenericRecord handling below) -
        in that situation we can't let the normal single-page
        offset/limit-per-call pattern run, because getAll()'s pagination
        advances by len(returned results) and a client-side filter can
        shrink that below what the server actually consumed, silently
        skipping or duplicating records once a query spans more than one
        page. Fetching everything up front and paginating the final,
        fully-filtered list ourselves (see callers) avoids that entirely."""
        items = []
        offset = 0
        while True:
            result = self._get(collection, filter=filt, offset=offset, limit=page_size)
            data = result.get("data", [])
            items.extend(data)
            if len(data) < page_size:
                break
            offset += len(data)
        return items

    # -----------------------------------------------------------------------------
    def getEntities(self, parentId, type, start, count):
        # CONFIRMED live (a_query.py's TypeError: many scripts pass
        # max_obj_count as the STRING "1000", not an int - harmless for the
        # old code path (offset/limit just get interpolated into the
        # request's query params either way), but the GenericRecord
        # fetch-then-slice path below does real `start:start+count` integer
        # arithmetic, which a string breaks. Coerce once up front so both
        # paths work regardless of what the caller passed.
        start, count = int(start), int(count)
        try:
            collection = self._resolve_parent_collection(parentId, type)
        except ValueError:
            # CONFIRMED live: a leaf/special entity (e.g. an
            # ExternalHostsZone under a view's zones) has no 'zones'
            # sub-collection at all - that's a legitimate "zero children of
            # this type" state, not an error. Scripts that recurse into
            # every returned entity unconditionally (zone_query_all.py's
            # printZone(), which calls getEntities() on every zone it finds,
            # including special leaf zones with no children of their own)
            # expect an empty list here, matching v1's forgiving behavior,
            # not an exception.
            return []
        filt = self._rr_type_filter(type)
        if type in self.FETCH_ALL_RR_TYPES:
            # CONFIRMED live (dump_rr.py -t ns; zone_rr_query.py -t host):
            # neither GenericRecord's recordType:in(...) filter nor (for
            # HostRecord, which has no recordType at all) any filter can
            # reliably exclude everything else server-side. Fetch whatever
            # the server filter lets through (None for HostRecord - the
            # whole collection), then drop anything that isn't actually
            # this type by its real top-level 'type' (which IS reliably
            # present on every record), then apply start/count to that
            # fully-correct list ourselves.
            raw = [o for o in self._fetch_all_raw(collection, filt) if o.get("type") == type]
            return [self._v2_to_v1(o) for o in raw[start:start + count]]
        result = self._get(collection, filter=filt, offset=start, limit=count)
        return [self._v2_to_v1(o) for o in result.get("data", [])]

    # -----------------------------------------------------------------------------
    def getEntitiesByName(self, parentId, name, type, start, count):
        # see getEntities() above for why this coercion is needed.
        start, count = int(start), int(count)
        try:
            collection = self._resolve_parent_collection(parentId, type)
        except ValueError:
            # see getEntities() above - no sub-collection of this type
            # means zero matches, not an error.
            return []
        if type in self.FETCH_ALL_RR_TYPES:
            # see getEntities() above for why these types need this
            # fetch-everything-then-filter-then-paginate treatment instead
            # of a single filtered offset/limit call.
            filt = self._rr_type_filter(type)
            if name:
                filt = "name:'%s' and %s" % (name, filt) if filt else "name:'%s'" % name
            raw = [o for o in self._fetch_all_raw(collection, filt) if o.get("type") == type]
            return [self._v2_to_v1(o) for o in raw[start:start + count]]
        filt_parts = []
        if name:
            filt_parts.append("name:'%s'" % name)
        rr_filt = self._rr_type_filter(type)
        if rr_filt:
            filt_parts.append(rr_filt)
        filt = " and ".join(filt_parts) if filt_parts else None
        result = self._get(collection, filter=filt, offset=start, limit=count)
        return [self._v2_to_v1(o) for o in result.get("data", [])]

    # -----------------------------------------------------------------------------
    def getEntityById(self, id):
        return self._v2_to_v1(self._get_by_id(id))

    # -----------------------------------------------------------------------------
    def getLinkedEntities(self, entityId, type, start, count):
        ent = self._get_by_id(entityId)
        if not ent:
            return []
        key = self._link_key(type)
        href = ent.get("_links", {}).get(key, {}).get("href")
        if not href:
            return []
        result = self._get(href, offset=start, limit=count)
        return [self._v2_to_v1(o) for o in result.get("data", [])]

    # -----------------------------------------------------------------------------
    # IP blocks/networks/DHCP ranges are identified by their CIDR/range, not
    # a free-text 'name' - v1's generic keyword search matched on whatever
    # field made sense for the object type, including the CIDR text for
    # these. Filtering these by 'name' (as a plain string search) 400s or
    # silently returns nothing, since 'name' isn't populated with the CIDR.
    _RANGE_IDENTIFIED_TYPES = {
        "IPv4Block", "IPv6Block", "IPv4Network", "IPv6Network",
        "IPv4DHCPRange", "IPv6DHCPRange",
    }

    def _get_configurations_cached(self):
        """PERFORMANCE: the configuration list rarely changes within a
        single script run, but was being re-fetched on every call to
        _find_range_entities() - including the redundant repeat calls
        described below. Cache it once per BAM instance."""
        if self._config_list_cache is None:
            self._config_list_cache = self._get("/api/v2/configurations", limit=1000).get("data", [])
        return self._config_list_cache

    def _find_range_entities(self, keyword, wanted_link_keys):
        """CONFIRMED: the generic root search endpoint (GET /api/v2) does
        NOT support filtering on 'range' at all - a live 400
        (InvalidFilterField) listed its supported fields and 'range' isn't
        among them (only name/type/id/configuration.*/etc.). There is also
        no global /api/v2/blocks or /api/v2/networks endpoint - blocks,
        networks, and DHCP ranges only exist nested under a Configuration
        (and blocks can nest further under other blocks). So replicate v1's
        "search every configuration" behavior by walking that hierarchy
        ourselves and filtering on 'range' at each typed sub-collection
        (which DOES support it per BlueCat's docs), instead of relying on
        the root search.

        PERFORMANCE notes:
        - Callers typically reach this via searchAllByObjectTypes(), which
          wraps searchByObjectTypes() in getAll()'s generic pagination loop
          (see getAll()). getAll() only stops once a call returns 0 rows, so
          for a small result set (usually 0 or 1 block/network) it was
          calling back in for a "next page" that repeated this ENTIRE tree
          walk a second time just to confirm there was nothing left. Results
          are now memoized per (keyword, wanted_link_keys) on this instance,
          so the second call is instant.
        - The tree walk itself only needs 'range'/'type'/'_links' to find a
          match and keep descending - fetching every field of every
          block/network/range under every configuration (the previous
          behavior) multiplies payload size for no benefit. This walk now
          requests a trimmed `fields` projection, and re-fetches the full
          representation (via the now-cached _get_by_id()) only for
          confirmed matches - so callers still get back a complete object,
          identical to before, just without paying for every non-match's
          full payload too.
        - The configuration list itself is cached (_get_configurations_cached).
        NOTE: still walks every block/network/range under every
        configuration when nothing matches early - kept deliberately simple
        (no depth limit) since correctness matters more than raw speed for
        an interactive lookup like this.
        """
        cache_key = (keyword, tuple(sorted(wanted_link_keys)))
        if cache_key in self._range_search_cache:
            return self._range_search_cache[cache_key]
        found_ids = []
        queue = list(self._get_configurations_cached())
        walk_fields = "id,type,range,_links"
        while queue:
            node = queue.pop(0)
            links = node.get("_links", {})
            for key in ("blocks", "networks", "ranges"):
                href = links.get(key, {}).get("href")
                if not href:
                    continue
                try:
                    page = self._get(href, fields=walk_fields, limit=1000)
                except ValueError:
                    continue
                for child in page.get("data", []):
                    if key in wanted_link_keys and child.get("range") == keyword:
                        found_ids.append(child["id"])
                    # descend - a block can itself contain nested blocks
                    # and/or networks, a network can contain ranges.
                    queue.append(child)
        # re-fetch full representations for confirmed matches only (also
        # warms the general _get_by_id() cache for anything downstream that
        # looks these ids up again, e.g. access_rights.py's getConfiguration()).
        found = [f for f in (self._get_by_id(i) for i in found_ids) if f]
        self._range_search_cache[cache_key] = found
        return found

    def searchByObjectTypes(self, keyword, types, start, count):
        type_list = types.split(",") if isinstance(types, str) else (types or [])
        # v1 type strings (e.g. "IP4Block") don't always match the v2 API's
        # actual 'type' filter enum (e.g. "IPv4Block") - translate them.
        normalized_types = [_v2_type_enum(t.strip()) for t in type_list if t.strip()]
        if keyword and normalized_types and all(t in self._RANGE_IDENTIFIED_TYPES for t in normalized_types):
            wanted_link_keys = set(self._link_key(t) for t in normalized_types)
            all_found = self._find_range_entities(keyword, wanted_link_keys)
            window = all_found[start:start + count]
            return [self._v2_to_v1(o) for o in window]
        filt_parts = []
        if keyword:
            filt_parts.append("name:contains('%s')" % keyword)
        quoted = ",".join("'%s'" % t for t in normalized_types)
        if quoted:
            filt_parts.append("type:in(%s)" % quoted)
        filt = " and ".join(filt_parts) if filt_parts else None
        result = self._get("/api/v2", filter=filt, offset=start, limit=count)
        return [self._v2_to_v1(o) for o in result.get("data", [])]

    # -----------------------------------------------------------------------------
    # addHostRecord() / addNAPTRRecord() / addSRVRecord() / addTXTRecord() /
    # addAliasRecord() / addGenericRecord()
    #
    # VERIFY: field names for AliasRecord/SRVRecord/NAPTRRecord/TXTRecord are
    # best-effort - confirm against the ResourceRecord schema in
    # http://{Address_Manager_IP}/api/docs and adjust if the server 400s.
    def addHostRecord(self, viewId, absoluteName, addresses, ttl, properties):
        zone_id, rel_name = self._zone_and_relname(viewId, absoluteName, properties)
        addr_list = [{"address": a.strip()} for a in str(addresses).split(",") if a.strip()]
        body = {"type": "HostRecord", "addresses": addr_list, **_name_field(rel_name)}
        norm_ttl = _normalize_ttl(ttl)
        if norm_ttl is not None:
            body["ttl"] = norm_ttl
        props = _v1_props_to_dict(properties)
        if "reverseRecord" in props:
            body["reverseRecord"] = str(props["reverseRecord"]).lower() == "true"
        collection = self._resolve_parent_collection(zone_id, "HostRecord")
        created = self._post(collection, body, headers=_same_as_zone_headers(rel_name)).json()
        return created.get("id", 0)

    def addNAPTRRecord(self, viewId, absolutename, order, preference, service, regexp, replacement, flags, ttl, properties):
        zone_id, rel_name = self._zone_and_relname(viewId, absolutename, properties)
        body = {
            "type": "NAPTRRecord", "order": order, "preference": preference,
            "service": service, "regularExpression": regexp, "replacement": replacement, "flags": flags,
            **_name_field(rel_name),
        }
        norm_ttl = _normalize_ttl(ttl)
        if norm_ttl is not None:
            body["ttl"] = norm_ttl
        collection = self._resolve_parent_collection(zone_id, "NAPTRRecord")
        created = self._post(collection, body, headers=_same_as_zone_headers(rel_name)).json()
        return created.get("id", 0)

    def addSRVRecord(self, viewId, absolutename, priority, port, weight, linkedRecordName, ttl, properties):
        zone_id, rel_name = self._zone_and_relname(viewId, absolutename, properties)
        # CONFIRMED live: v2's real field is 'linkedRecord', a nested
        # {id, type, ...} reference (not v1's flat 'linkedRecordName'
        # string), and the server requires linkedRecord.type explicitly
        # (MissingRequiredField) - _resolve_linked_record() looks the
        # target up by name to get both.
        body = {
            "type": "SRVRecord", "priority": priority, "port": port,
            "weight": weight, "linkedRecord": self._resolve_linked_record(linkedRecordName),
            **_name_field(rel_name),
        }
        norm_ttl = _normalize_ttl(ttl)
        if norm_ttl is not None:
            body["ttl"] = norm_ttl
        collection = self._resolve_parent_collection(zone_id, "SRVRecord")
        created = self._post(collection, body, headers=_same_as_zone_headers(rel_name)).json()
        return created.get("id", 0)

    def addTXTRecord(self, viewId, absoluteName, txt, ttl, properties):
        zone_id, rel_name = self._zone_and_relname(viewId, absoluteName, properties)
        body = {"type": "TXTRecord", "text": txt, **_name_field(rel_name)}
        norm_ttl = _normalize_ttl(ttl)
        if norm_ttl is not None:
            body["ttl"] = norm_ttl
        collection = self._resolve_parent_collection(zone_id, "TXTRecord")
        created = self._post(collection, body, headers=_same_as_zone_headers(rel_name)).json()
        return created.get("id", 0)

    def addAliasRecord(self, viewid, absoluteName, linkedRecordName, ttl, properties):
        zone_id, rel_name = self._zone_and_relname(viewid, absoluteName, properties)
        # same 'linkedRecord' + required-type handling as addSRVRecord()
        # (see comment there).
        body = {"type": "AliasRecord", "linkedRecord": self._resolve_linked_record(linkedRecordName), **_name_field(rel_name)}
        norm_ttl = _normalize_ttl(ttl)
        if norm_ttl is not None:
            body["ttl"] = norm_ttl
        collection = self._resolve_parent_collection(zone_id, "AliasRecord")
        created = self._post(collection, body, headers=_same_as_zone_headers(rel_name)).json()
        return created.get("id", 0)

    def addGenericRecord(self, viewid, add_absolutename, type, rdata, ttl, properties):
        zone_id, rel_name = self._zone_and_relname(viewid, add_absolutename, properties)
        # CONFIRMED WORKING (per an independently-built v2 shim from another
        # engineer, shared live 2026-09-21: BAM-jerry.py's addResourceRecord()):
        # a zone-apex ("-k" / same-as-zone) record is signaled via the
        # 'x-bcn-same-as-zone: true' REQUEST HEADER, not any body-level
        # 'name' value - 'name' must be entirely ABSENT from the body when
        # this header is set. This explains why blank/null/omitted/'@' all
        # either 400'd or produced a wrong literal record in this shim's own
        # earlier live testing (debug_genericrecord_apex*.py) - none of
        # those tried the header route. This server's v2 model wraps
        # records created this way under the top-level type "GenericRecord",
        # with the real DNS type (A, NS, MX, ...) in a separate 'recordType'
        # field - confirmed separately from a live GET of an existing record
        # (see _v2_to_v1's 'recordType' handling above).
        body = {"type": "GenericRecord", "recordType": type, "rdata": rdata, **_name_field(rel_name)}
        # v1 scripts (e.g. ns_add.py) pass ttl="-1" meaning "no explicit TTL
        # - use the zone default"; v2 rejects a negative ttl outright
        # (400 ValueOutsideRange), so omit the field entirely in that case.
        norm_ttl = _normalize_ttl(ttl)
        if norm_ttl is not None:
            body["ttl"] = norm_ttl
        collection = self._resolve_parent_collection(zone_id, "GenericRecord")
        created = self._post(collection, body, headers=_same_as_zone_headers(rel_name)).json()
        return created.get("id", 0)

    # -----------------------------------------------------------------------------
    def addEntity(self, parentId, data):
        ttype = data.get("type")
        collection = self._resolve_parent_collection(parentId, ttype)
        # CONFIRMED live (macPool_add.py: InvalidResourceId on field 'id') -
        # v1 scripts build this dict by hand and always include "id": 0 as a
        # placeholder (v1 ignored it and assigned the real id on create).
        # v2's create endpoint doesn't want a client-supplied 'id' field at
        # all, even a placeholder 0 - drop it along with 'type' (handled
        # separately below).
        body = {k: v for k, v in data.items() if k not in ("type", "id")}
        # translate v1-style type strings (e.g. "IP4Block") to the real v2
        # 'type' enum value (e.g. "IPv4Block") before sending.
        body["type"] = _v2_type_enum(ttype)
        created = self._post(collection, body).json()
        return created.get("id", 0)

    # -----------------------------------------------------------------------------
    def delete(self, objectId):
        ent = self._get_by_id(objectId)
        if not ent:
            raise ValueError("Entity id %s not found" % objectId)
        href = ent.get("_links", {}).get("self", {}).get("href")
        if not href:
            raise ValueError("Entity id %s has no self link" % objectId)
        self._req("DELETE", href)
        self._invalidate_entity_cache(objectId)
        return

    # -----------------------------------------------------------------------------
    # CONFIRMED live (a_update.py's JsonDeserializationError: "resource
    # field 'configuration' failed; expected type was <Configuration>"):
    # the classic read-modify-write script pattern - fetch an entity,
    # `properties = bam.splitProp(ent)`, change ONE scalar (e.g. rdata),
    # `ent['properties'] = bam.joinProp(properties)`, then bam.update(ent) -
    # round-trips EVERY field through the pipe-delimited properties string,
    # not just the one the script actually changed. _v2_to_v1() encodes
    # nested v2 objects (a record's 'configuration'/'view' back-references,
    # 'userDefinedFields', 'linkedRecord') into that same string same as any
    # scalar; _v1_props_for_write() decodes it back as a plain STRING (a
    # Python repr), not a real JSON object, and the server rejects that.
    # update() already re-fetches the entity fresh, which has the correct,
    # un-corrupted value for these - the script never intended to change a
    # relationship/reference field via this pattern anyway, so just drop
    # them from the overlay instead of letting a corrupted string clobber
    # the good value. Extend this set if another nested-object field turns
    # up the same way.
    #
    # 'type' belongs here too, for a related but distinct reason (CONFIRMED
    # live: InvalidResourceType, "acceptedTypes": [...real v2 types...]).
    # _v2_to_v1() deliberately overwrites properties['type'] with the short
    # DNS mnemonic for GenericRecord-wrapped records (e.g. 'A' instead of
    # 'GenericRecord') so `properties['type']=="A"`-style checks in scripts
    # keep working - update() below keeps the REAL type from the freshly
    # re-fetched `current` (the server requires 'type' in the PUT body), so
    # that synthetic v1-only value must never be let back in through the
    # overlay to clobber it.
    # 'exclusionRanges'/'usage' (DHCP4Range/DHCP6Range) belong here for the
    # exact same nested-object-corrupted-into-a-string reason (CONFIRMED
    # live via dhcp4range_update.py: JsonDeserializationError, "expected
    # type was [<ip_range>]" - the real empty list [] from `current` got
    # overwritten by the literal string "[]" round-tripped through the
    # properties string). 'usage' is also a nested/computed object and
    # would hit the same failure mode if it were ever included.
    UPDATE_SKIP_PROPS = {
        "configuration", "view", "userDefinedFields", "linkedRecord",
        "_embedded", "type", "exclusionRanges", "usage",
        # 'excludeDHCPRange' is a v1-only SYNTHETIC key (see _v2_to_v1()'s
        # DHCP4Range/DHCP6Range handling) with no matching real v2 field at
        # all - it always round-trips through splitProp()/joinProp() intact
        # even when a script only meant to change 'range' (dhcp4range_
        # update.py does exactly this), so it must never be sent to the API.
        "excludeDHCPRange",
    }

    def update(self, data):
        """v1's update() PUTs a whole entity dict (typically fetched via
        getEntityByName/getEntitiesByName, modified via splitProp()/
        joinProp(), then passed straight back here). Re-fetch the current
        v2 representation and overlay only the decoded 'properties' fields
        (plus 'name' if given) so unrelated fields are never clobbered by
        v2's full-replace PUT semantics."""
        ent_id = data.get("id") if isinstance(data, dict) else None
        current = self._get_by_id(ent_id) if ent_id else None
        href = None
        if isinstance(data, dict):
            href = data.get("_links", {}).get("self", {}).get("href")
        if not current and href:
            current = self._get(href)
        if not current:
            raise ValueError("update(): could not resolve entity id %s" % ent_id)
        href = current["_links"]["self"]["href"]
        # CONFIRMED live: the server requires 'type' in the PUT body
        # (MissingRequiredField) and wants the REAL v2 type (e.g.
        # "GenericRecord"), not the synthetic short mnemonic
        # properties['type'] carries for scripts' benefit - keep it from
        # `current` (still overwritable by data["name"] etc. below, but
        # UPDATE_SKIP_PROPS keeps the overlay's synthetic version from ever
        # clobbering it).
        merged = {k: v for k, v in current.items() if k not in ("id", "_links")}
        # write-side helper translates any v1-aliased property (e.g.
        # Zone's 'deployable') to its real v2 field name/type before merging
        # - see V1_PROP_FIELD_ALIAS.
        overlay = _v1_props_for_write(data.get("properties", "") or "")
        for k in self.UPDATE_SKIP_PROPS:
            overlay.pop(k, None)
        # CONFIRMED live (host_add_one.py: an appended IP was silently
        # never persisted - two calls in a row each only ever saw the
        # ORIGINAL single-address list, because the generic list/dict-drop
        # rule just below unconditionally discarded HostRecord's
        # 'addresses' overlay every time, thinking it was corrupted
        # round-trip noise like exclusionRanges/_inheritedFields). Unlike
        # those fields, a script changing 'addresses' via splitProp()/
        # joinProp() (host_add_one.py's whole job) carries real intent -
        # convert the v1 comma-separated-IP-string overlay back to the
        # real v2 shape (a list of {'address': ip} objects) and merge it
        # directly, instead of letting the generic rule below drop it.
        if isinstance(overlay.get("addresses"), str) and isinstance(current.get("addresses"), list):
            ip_list = [a.strip() for a in overlay["addresses"].split(",") if a.strip()]
            merged["addresses"] = [{"address": ip} for ip in ip_list]
            overlay.pop("addresses", None)
        # CONFIRMED live (dhcp4range_update.py: JsonDeserializationError on
        # 'exclusionRanges', then again on '_inheritedFields') - ANY field
        # whose real value is a list/dict (not just the ones named in
        # UPDATE_SKIP_PROPS above) gets corrupted into a Python-repr STRING
        # by the properties-string round-trip, and the server rejects that
        # string in place of the real type. Rather than enumerate every
        # such field one 400 at a time, drop any overlay key here whose
        # CURRENT (real, un-corrupted) value is a list or dict - the script
        # never intended to change a nested/complex field through this
        # scalar-only properties mechanism anyway, so `current`'s original
        # value is always what should be kept.
        for k in list(overlay.keys()):
            if isinstance(current.get(k), (list, dict)):
                overlay.pop(k, None)
        merged.update(overlay)
        if data.get("name") is not None:
            merged["name"] = data["name"]
        self._req("PUT", href, json=merged)
        if ent_id:
            self._invalidate_entity_cache(ent_id)
        return

    # -----------------------------------------------------------------------------
    # response policy items (RPZ)
    def searchResponsePolicyItems(self, keyword, scope, start, count, properties, debug=False):
        filt = "name:contains('%s')" % keyword if keyword else None
        result = self._get("/api/v2/policyItems", filter=filt, offset=start, limit=count)
        data = [self._v2_to_v1(o) for o in result.get("data", [])]
        if debug:
            print('\ndebug: --- bam.searchResponsePolicyItems() ---')
            print(data)
            print('--- End of bam.searchResponsePolicyItems() ---\n')
        return data

    def addResponsePolicyItem(self, policy_id, item_name, options):
        policy = self._get_by_id(policy_id)
        if not policy:
            raise ValueError("Response policy id %s not found" % policy_id)
        href = policy.get("_links", {}).get("policyItems", {}).get("href")
        if not href:
            raise ValueError("Response policy id %s has no policyItems sub-collection" % policy_id)
        body = {"type": "ResponsePolicyItem", "name": item_name}
        try:
            self._post(href, body)
            return "True"     # matches v1: "True" = item added
        except ValueError:
            return "False"    # matches v1: "False" = item already exists

    def deleteResponsePolicyItem(self, policy_id, item_name, options):
        result = self._get("/api/v2/policyItems", filter="name:'%s'" % item_name)
        data = result.get("data", [])
        if not data:
            return "0"   # matches v1: item does not exist
        self._req("DELETE", data[0]["_links"]["self"]["href"])
        return "1"       # matches v1: item successfully deleted

    def uploadResponsePolicyFile(self, fileName, parentId):
        if not os.path.isfile(fileName):
            raise ValueError("Upload file not found")
        policy = self._get_by_id(parentId)
        href = policy.get("_links", {}).get("imports", {}).get("href") if policy else None
        if not href:
            raise ValueError("Response policy id %s has no imports sub-collection" % parentId)
        with open(fileName, 'rb') as fh:
            myfiles = {'data': (fileName, fh)}
            response = self.session.post(self._url(href),
                                          headers={"Authorization": self.header.get("Authorization")},
                                          files=myfiles, verify=False, timeout=self.req_timeout)
        if not response.ok:
            self._raise_for_error(response)
        return response

    def uploadResponsePolicyItems(self, fileName, parentId):
        # v1 deprecated this in favor of uploadResponsePolicyFile(); kept for
        # backward compatibility with scripts that still call it.
        return self.uploadResponsePolicyFile(fileName, parentId)

    # -----------------------------------------------------------------------------
    def addZone(self, parentId, absoluteName, properties):
        parent = self._get_by_id(parentId)
        if not parent:
            raise ValueError("Parent id %s not found" % parentId)
        href = parent.get("_links", {}).get("zones", {}).get("href")
        if not href:
            raise ValueError("Parent id %s (%s) has no zones sub-collection" % (parentId, parent.get("type")))
        body = {"type": "Zone", "name": absoluteName}
        # use the write-side helper (not raw _v1_props_to_dict) so the v1
        # 'deployable' property zone_add.py sends gets translated to the
        # real v2 'deploymentEnabled' boolean field (see V1_PROP_FIELD_ALIAS).
        body.update(_v1_props_for_write(properties))
        created = self._post(href, body).json()
        return created.get("id", 0)

    # -----------------------------------------------------------------------------
    # DNS deployment roles
    def addDNSDeploymentRole(self, entityId, serverInterfaceId, type, properties):
        return self._add_deployment_role(entityId, serverInterfaceId, type, properties, "DNSDeploymentRole")

    def _add_deployment_role(self, entityId, serverInterfaceId, type, properties, resource_type):
        # CONFIRMED live (dnsRole_add.py -r PRIMARY: InvalidResourceType,
        # acceptedTypes: ["DNSDeploymentRole"]) - the resource's 'type'
        # field is a FIXED value per role kind ("DNSDeploymentRole"/
        # "DHCPDeploymentRole"), not the v1 role-type string (PRIMARY/
        # SECONDARY/etc.) that scripts pass in as `type` here. A live GET
        # of an existing role (debug_tftp_deploy2.py) confirmed the actual
        # role kind goes in a separate 'roleType' field instead
        # (e.g. {"type": "DNSDeploymentRole", "roleType": "PRIMARY"}).
        ent = self._get_by_id(entityId)
        if not ent:
            raise ValueError("Entity id %s not found" % entityId)
        href = ent.get("_links", {}).get("deploymentRoles", {}).get("href")
        if not href:
            raise ValueError("Entity id %s has no deploymentRoles sub-collection" % entityId)
        # CONFIRMED live (dnsRole_add.py -r PRIMARY, next 400 after the
        # 'type' fix above): MissingRequiredField for 'interfaces' -
        # 'serverInterface' (singular) was wrong; the real field is
        # 'interfaces', a LIST of nested interface-reference objects, each
        # needing its own 'type' discriminator (server's acceptedType:
        # NetworkInterface | PublishedInterface | ServerGroupInterface).
        # dnsRole_add.py resolves serverInterfaceId via
        # getEntityByName(serverid, fullhostname, "NetworkServerInterface")
        # (see TYPE_LINK_KEY's 'NetworkServerInterface' -> 'interfaces'
        # mapping), i.e. a real v2 NetworkInterface id - use that
        # discriminator.
        body = {
            "type": resource_type,
            "roleType": type,
            "interfaces": [{"id": serverInterfaceId, "type": "NetworkInterface"}],
        }
        body.update(_v1_props_to_dict(properties))
        created = self._post(href, body).json()
        return created.get("id", 0)

    def deleteDNSDeploymentRole(self, entityId, serverInterfaceId):
        role = self.getDNSDeploymentRole(entityId, serverInterfaceId)
        if not role.get("id"):
            return
        self._req("DELETE", role["_links"]["self"]["href"])
        return

    def describeInterface(self, interfaceId):
        """Format a NetworkInterface/PublishedInterface for display, same
        'type:name(address)' shape as the interfaceInfo synthesized by
        getDNSDeploymentRoles()/getDNSDeploymentRolesByServer() - used by
        dnsRole_update.py to show the resulting role's interface in its
        success message. CONFIRMED live (debug_publishedinterface2.py): a
        NetworkInterface's address field is 'managementAddress'/
        'servicesIpv4Address'; a PublishedInterface's is 'primaryAddress'."""
        iface = self._get_by_id(interfaceId)
        if not iface:
            return ""
        addr = iface.get("managementAddress") or iface.get("servicesIpv4Address") or iface.get("primaryAddress") or ""
        return "%s:%s(%s)" % (iface.get("type", ""), iface.get("name", ""), addr)

    def setDNSDeploymentRoleInterface(self, roleId, interfaceId, interfaceType):
        """New helper for dnsRole_update.py's '--np' (move an existing role
        to a different published interface). update() can't do this -
        'interfaces' is a sub-collection reached only via the role's own
        '_links.interfaces.href' (CONFIRMED live via debug_dnsrole.py), not
        an inline field, so it's unconditionally stripped by update()'s
        list/dict guard even if a caller tried to route it through the
        v1-properties overlay. Send it as a direct field on a raw PUT to
        the role's own resource instead - the same 'interfaces': [{'id',
        'type'}] shape the create-time POST body uses (see
        _add_deployment_role() above). UNVERIFIED live: if the server
        rejects 'interfaces' on PUT the same way it wants it on POST, the
        real mechanism is likely a dedicated add/remove call against the
        role's own interfaces href instead of a field on the role's own
        PUT - report the exact error back if this 400s."""
        current = self._get_by_id(roleId)
        if not current:
            raise ValueError("DNS Deployment role id %s not found" % roleId)
        href = current["_links"]["self"]["href"]
        merged = {k: v for k, v in current.items() if k not in ("id", "_links")}
        merged["interfaces"] = [{"id": interfaceId, "type": interfaceType}]
        self._req("PUT", href, json=merged)
        self._invalidate_entity_cache(roleId)
        return

    def getDNSDeploymentRole(self, entityId, serverInterfaceId):
        # CONFIRMED live (dnsRole_delete.py -r master: InvalidFilterField)
        # - a role's assigned interface can't be filtered server-side at
        # all on this endpoint (supportedFilterFields: ancestor.id,
        # configuration.id/name, id, name, nsRecordTtl, roleType, view.id/
        # name, _embedded.tags*). CONFIRMED live (debug_dnsrole.py): a
        # role's 'interfaces' isn't even an inline field on the role
        # itself (list or single GET) - it's a separate sub-collection,
        # reached via the role's own '_links.interfaces.href'. So: fetch
        # every role under this entity (small, unpaginated list in
        # practice - a zone/view/config typically has only a handful of
        # deployment roles), then check each one's own interfaces
        # sub-collection for a matching id.
        ent = self._get_by_id(entityId)
        href = ent.get("_links", {}).get("deploymentRoles", {}).get("href") if ent else None
        if not href:
            return self._v2_to_v1(None)
        result = self._get(href)
        for role in result.get("data", []):
            ifaces_href = role.get("_links", {}).get("interfaces", {}).get("href")
            if not ifaces_href:
                continue
            ifaces = self._get(ifaces_href).get("data", [])
            if any(str(i.get("id")) == str(serverInterfaceId) for i in ifaces):
                v1_role = self._v2_to_v1(role)
                # v1's own getDNSDeploymentRole() returned the ROLE TYPE
                # (e.g. "MASTER") in the top-level 'type' field - unlike
                # every other entity, where 'type' is the resource's own
                # kind ("DNSDeploymentRole" here). dnsRole_delete.py
                # compares `rtn_role['type'] == roletype` directly (not via
                # splitProp()), so override just for this method's return
                # value with the real v2 roleType (e.g. "PRIMARY") -
                # scripts must pass the same translated v1->v2 roleType
                # word (see dnsRole_add.py's MASTER->PRIMARY etc. mapping)
                # for this comparison to match.
                v1_role["type"] = role.get("roleType", v1_role["type"])
                return v1_role
        return self._v2_to_v1(None)

    def getDNSDeploymentRoleByServer(self, entityId, serverId):
        """Per explicit request (dnsRole_delete.py should match purely by
        -r role + -s server name, no -p/interface disambiguation): like
        getDNSDeploymentRole() above, but matches ANY interface (Network OR
        Published) belonging to the given server - CONFIRMED live
        (debug_publishedinterface.py) that a PublishedInterface object also
        carries a 'server': {'id','name',...} back-reference, same as a
        plain NetworkInterface, so this works for a role attached via
        either interface type without the caller having to know or care
        which one is actually in use."""
        ent = self._get_by_id(entityId)
        href = ent.get("_links", {}).get("deploymentRoles", {}).get("href") if ent else None
        if not href:
            return self._v2_to_v1(None)
        result = self._get(href)
        for role in result.get("data", []):
            ifaces_href = role.get("_links", {}).get("interfaces", {}).get("href")
            if not ifaces_href:
                continue
            for iface in self._get(ifaces_href).get("data", []):
                server = iface.get("server")
                if isinstance(server, dict) and str(server.get("id")) == str(serverId):
                    v1_role = self._v2_to_v1(role)
                    v1_role["type"] = role.get("roleType", v1_role["type"])
                    return v1_role
        return self._v2_to_v1(None)

    def getDNSDeploymentRolesByServer(self, entityId, serverId):
        """Per explicit request (dnsRole_query.py's -s should LIST every
        role matching the server, no -p/interface disambiguation): like
        getDNSDeploymentRoleByServer() above, but returns every matching
        role instead of just the first - a server can carry more than one
        role (e.g. a plain DNS role plus one via a published interface)."""
        ent = self._get_by_id(entityId)
        href = ent.get("_links", {}).get("deploymentRoles", {}).get("href") if ent else None
        if not href:
            return []
        result = self._get(href)
        roles = []
        for role in result.get("data", []):
            ifaces_href = role.get("_links", {}).get("interfaces", {}).get("href")
            if not ifaces_href:
                continue
            matched_ifaces = [
                i for i in self._get(ifaces_href).get("data", [])
                if isinstance(i.get("server"), dict) and str(i["server"].get("id")) == str(serverId)
            ]
            if matched_ifaces:
                v1_role = self._v2_to_v1(role)
                v1_role["type"] = role.get("roleType", v1_role["type"])
                # Per explicit request: also surface the matched
                # interface(s) (type/name/address) so the caller can
                # display which interface each role is attached to.
                iface_descs = []
                for i in matched_ifaces:
                    # CONFIRMED live (debug_publishedinterface2.py): a
                    # NetworkInterface's address is 'managementAddress'/
                    # 'servicesIpv4Address', but a PublishedInterface has
                    # neither - its address field is 'primaryAddress'.
                    addr = i.get("managementAddress") or i.get("servicesIpv4Address") or i.get("primaryAddress") or ""
                    iface_descs.append("%s:%s(%s)" % (i.get("type", ""), i.get("name", ""), addr))
                props = _v1_props_to_dict(v1_role.get("properties") or "")
                props["interfaceInfo"] = ",".join(iface_descs)
                v1_role["properties"] = _dict_to_v1_props(props)
                roles.append(v1_role)
        return roles

    def getDNSDeploymentRoles(self, entityId):
        """New helper (no v1 equivalent) for dnsRole_query.py's '-a' (list
        every role under a zone/view/config, with the server each is
        assigned to). Same 'type' override as getDNSDeploymentRole() above
        (real roleType, e.g. "PRIMARY"), plus a synthesized 'serverName'/
        'serverNames' property resolved from each role's own interfaces
        sub-collection - CONFIRMED live (debug_server.py's interfaces
        dump) that a NetworkInterface carries a 'server': {'id','name',...}
        back-reference, so the assigned server's name is available from
        there without a second lookup per role."""
        ent = self._get_by_id(entityId)
        href = ent.get("_links", {}).get("deploymentRoles", {}).get("href") if ent else None
        if not href:
            return []
        result = self._get(href)
        roles = []
        for role in result.get("data", []):
            v1_role = self._v2_to_v1(role)
            v1_role["type"] = role.get("roleType", v1_role["type"])
            server_names = []
            iface_descs = []
            ifaces_href = role.get("_links", {}).get("interfaces", {}).get("href")
            if ifaces_href:
                for iface in self._get(ifaces_href).get("data", []):
                    server = iface.get("server")
                    if isinstance(server, dict) and server.get("name"):
                        server_names.append(server["name"])
                    # Per explicit request: also surface each interface's
                    # type/name/address alongside the role. CONFIRMED live
                    # (debug_publishedinterface2.py): a PublishedInterface's
                    # address field is 'primaryAddress', not
                    # 'managementAddress'/'servicesIpv4Address'.
                    addr = iface.get("managementAddress") or iface.get("servicesIpv4Address") or iface.get("primaryAddress") or ""
                    iface_descs.append("%s:%s(%s)" % (iface.get("type", ""), iface.get("name", ""), addr))
            props = _v1_props_to_dict(v1_role.get("properties") or "")
            props["serverName"] = ",".join(server_names)
            props["interfaceInfo"] = ",".join(iface_descs)
            v1_role["properties"] = _dict_to_v1_props(props)
            roles.append(v1_role)
        return roles

    # -----------------------------------------------------------------------------
    # DNS/DHCP deployment options
    def getDNSDeploymentOption(self, entityId, name, serverId):
        return self._get_deployment_option(entityId, name, serverId)

    def _get_deployment_option(self, entityId, name, serverId):
        # CONFIRMED live (dns_forwardingPolicy_delete.py -c config1:
        # InvalidFilterField 'server.id', supportedFilterFields: ancestor.id,
        # code, configuration.id/name, id, name, serverScope.id, type, value,
        # _embedded.tags*) - two bugs here: (1) the filter field is really
        # 'serverScope.id', not 'server.id'; (2) callers pass the v1 sentinel
        # "0" (a STRING) to mean "no server filter", which `if serverId:`
        # treated as truthy (a non-empty string), so the filter was always
        # applied - even for the config/view-level (no -s/-g) case, which
        # then filtered for a nonexistent 'serverScope.id:0' and never
        # matched. Treat "0" (string or int) the same as falsy here.
        ent = self._get_by_id(entityId)
        href = ent.get("_links", {}).get("deploymentOptions", {}).get("href") if ent else None
        if not href:
            return self._v2_to_v1(None)
        filt = "name:'%s'" % name
        # CONFIRMED live (dns_forwardingPolicy_delete.py -c config1 -s dds1
        # -y: "does not exist" even though the option WAS there) - only
        # scope by serverScope.id when looking up an option under a
        # config/view that's been scoped DOWN to a server/serverGroup, not
        # when entityId already IS that server/serverGroup. The -y (direct
        # add_to_server_input) callers pass the SAME id as both entityId and
        # serverId in that case, since the option is a direct child of the
        # server's/serverGroup's own deploymentOptions collection with no
        # separate serverScope reference on it at all - adding the filter
        # there requires a self-referencing serverScope that doesn't exist,
        # so it never matches.
        if serverId and str(serverId) not in ("0", str(entityId)):
            filt += " and serverScope.id:%s" % serverId
        result = self._get(href, filter=filt)
        data = result.get("data", [])
        opt = data[0] if data else None
        v1_opt = self._v2_to_v1(opt)
        # CONFIRMED live (dns_forwardingPolicy_delete.py -c config1:
        # KeyError 'value') - v1's own getDNSDeploymentOption() returned the
        # option's value directly in a top-level 'value' key (scripts do
        # `ent['value']`, not `bam.splitProp(ent)['value']`); _v2_to_v1()
        # only encodes it into the properties string like any other field,
        # same situation as getDNSDeploymentRole()'s 'type' override above.
        if opt is not None:
            real_value = opt.get("value")
            # CONFIRMED live (dns_forwarding_delete.py -c config1:
            # AttributeError 'list' object has no attribute 'split') - the
            # 'forwarding' option's real v2 value is a JSON array (see
            # _add_deployment_option()'s write-side note above), but v1
            # scripts do `ent['value'].split(",")` expecting the single
            # comma-joined STRING v1 itself returned. Re-join it back into
            # that same string here so those scripts keep working
            # unchanged; a plain scalar value (e.g. "forwarding-policy"'s
            # "FIRST"/"ONLY") passes through as-is.
            if isinstance(real_value, list):
                real_value = ",".join(str(v) for v in real_value)
            v1_opt["value"] = real_value
        return v1_opt

    def addDNSDeploymentOption(self, entityId, name, value, properties):
        # CONFIRMED live (dns_forwardingPolicy_add.py -o: MissingRequiredField
        # 'type', acceptedTypes: DHCPv4ClientOption/DHCPv4RawOption/
        # DHCPv4ServiceOption/DHCPv6ClientOption/DHCPv6RawOption/
        # DHCPv6ServiceOption/DHCPVendorOption/DNSOption/DNSRawOption/
        # StartOfAuthority) - like deployment roles, a deployment option
        # resource requires a fixed 'type' discriminator per option kind;
        # the plain name/value DNS option (forwarding-policy, forwarding,
        # match-clients, etc.) is 'DNSOption'.
        return self._add_deployment_option(entityId, name, value, properties, "DNSOption")

    def _add_deployment_option(self, entityId, name, value, properties, resource_type):
        ent = self._get_by_id(entityId)
        if not ent:
            raise ValueError("Entity id %s not found" % entityId)
        href = ent.get("_links", {}).get("deploymentOptions", {}).get("href")
        if not href:
            raise ValueError("Entity id %s has no deploymentOptions sub-collection" % entityId)
        # CONFIRMED live (dns_forwarding_add.py -i 8.8.8.8 -z yes:
        # InvalidResourceFieldValue on 'value', valueFormat: ["(yes | no)",
        # "<ip_address>"]) - the 'forwarding' DNSOption's real v2 'value'
        # field is a JSON ARRAY (first element the yes/no disable-for-
        # child-zone flag, followed by one or more forwarder IP addresses),
        # not the single comma-joined STRING v1 used
        # ("yes,8.8.8.8,1.1.1.1"). Split it back into a list here so the
        # script itself never has to change.
        #
        # CONFIRMED live (matchClient_add.py -m 203.0.113.0/24:
        # JsonDeserializationError on 'value', expected type []) - the
        # "match-clients" DNSOption's value is a JSON array too (each
        # element a client-matching entry, e.g. a CIDR or "any"), same as
        # "forwarding". This was found via matchClient_query.py, which
        # already worked (a pre-existing "match-clients" option's array
        # value gets rejoined into a v1-style comma string by
        # _get_deployment_option() below) - only the ADD path was missing
        # the same list conversion.
        ARRAY_VALUE_OPTION_NAMES = ("forwarding", "match-clients")
        if name in ARRAY_VALUE_OPTION_NAMES and isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip() != ""]
        body = {"type": resource_type, "name": name, "value": value}
        props = _v1_props_to_dict(properties)
        # CONFIRMED live (dns_forwardingPolicy_add.py -c config1 -v view1
        # -s dds1: option landed on the VIEW instead of on the server under
        # it) - scripts pass v1's 'server=<id>'/'serverGroup=<id>' property
        # to scope an option to a server/serverGroup under the given
        # config/view. That plain 'server'/'serverGroup' field isn't a real
        # v2 field on a deployment option - it was silently accepted and
        # ignored by the POST. getDNSDeploymentOption()'s confirmed filter
        # field 'serverScope.id' implies the real write-side field is
        # 'serverScope', a nested reference object (like the 'interfaces'/
        # 'configuration' reference shapes elsewhere in this file), not a
        # bare id. UNVERIFIED live whether 'type' inside it needs to be
        # exactly 'Server'/'ServerGroup' - report the exact error back if
        # this still doesn't scope correctly.
        server_id = props.pop("server", None)
        servergroup_id = props.pop("serverGroup", None)
        if server_id:
            body["serverScope"] = {"id": server_id, "type": "Server"}
        elif servergroup_id:
            body["serverScope"] = {"id": servergroup_id, "type": "ServerGroup"}
        body.update(props)
        created = self._post(href, body).json()
        return created.get("id", 0)

    def deleteDNSDeploymentOption(self, entityId, name, serverId):
        opt = self.getDNSDeploymentOption(entityId, name, serverId)
        if not opt.get("id"):
            return
        self._req("DELETE", opt["_links"]["self"]["href"])
        return

    def updateDNSDeploymentOption(self, data):
        return self.update(data)

    # DHCP-side deployment roles/options reuse the exact same v2 mechanics
    def addDHCPDeploymentRole(self, entityId, serverInterfaceId, type, properties):
        return self._add_deployment_role(entityId, serverInterfaceId, type, properties, "DHCPDeploymentRole")

    # NOTE: no CLI script currently calls the DHCP-side option wrappers
    # below (only addDNSDeploymentOption is exercised live so far) - their
    # 'type' values are a best-effort pick from the same acceptedTypes list
    # addDNSDeploymentOption's error surfaced, NOT yet confirmed live.
    # Fix the specific mapping here if/when a script hits a 400 on one.
    def addDHCPClientDeploymentOption(self, entityId, name, value, properties):
        return self._add_deployment_option(entityId, name, value, properties, "DHCPv4ClientOption")

    def addDHCPServiceDeploymentOption(self, entityId, name, value, properties):
        return self._add_deployment_option(entityId, name, value, properties, "DHCPv4ServiceOption")

    def getDHCPServiceDeploymentOption(self, entityId, name, serverId):
        return self._get_deployment_option(entityId, name, serverId)

    def updateDHCPServiceDeploymentOption(self, data):
        return self.update(data)

    def addDHCPVendorDeploymentOption(self, entityId, name, value, properties):
        return self._add_deployment_option(entityId, name, value, properties, "DHCPVendorOption")

    def addDHCP6ClientDeploymentOption(self, entityId, name, value, properties):
        return self._add_deployment_option(entityId, name, value, properties, "DHCPv6ClientOption")

    def addDHCP6ServiceDeploymentOption(self, entityId, name, value, properties):
        return self._add_deployment_option(entityId, name, value, properties, "DHCPv6ServiceOption")

    def addRawDeploymentOption(self, entityId, name, value, properties):
        return self._add_deployment_option(entityId, name, value, properties, "DNSRawOption")

    # -----------------------------------------------------------------------------
    # DHCP match classes / sub-classes
    def addDHCPMatchClass(self, configurationId, name, matchCriteria, properties):
        collection = self._resolve_parent_collection(configurationId, "ClientClass")
        # VERIFY: "ClientClass" isn't a real v2 type enum value (confirmed
        # from a live 400's accepted-values list) - _v2_type_enum() maps it
        # to "DHCPv4ClientClass" as a best guess; adjust if this 400s.
        body = {"type": _v2_type_enum("ClientClass"), "name": name, "matchCriteria": matchCriteria}
        body.update(_v1_props_to_dict(properties))
        created = self._post(collection, body).json()
        return created.get("id", 0)

    def addDHCPSubClass(self, matchClassId, matchValue, properties):
        parent = self._get_by_id(matchClassId)
        if not parent:
            raise ValueError("Match class id %s not found" % matchClassId)
        href = parent.get("_links", {}).get("subclasses", {}).get("href")
        if not href:
            raise ValueError("Match class id %s has no subclasses sub-collection" % matchClassId)
        # VERIFY: real v2 enum for a subclass is most likely "DHCPv4Subclass"
        # (per the accepted-values list), not "ClientClass" - untested live.
        body = {"type": "DHCPv4Subclass", "matchValue": matchValue}
        body.update(_v1_props_to_dict(properties))
        created = self._post(href, body).json()
        return created.get("id", 0)

    # -----------------------------------------------------------------------------
    # DHCP ranges
    def addDHCP4Range(self, networkId, start, end, properties):
        collection = self._resolve_parent_collection(networkId, "DHCP4Range")
        body = {"type": _v2_type_enum("DHCP4Range"), "range": "%s-%s" % (start, end)}
        body.update(_v1_props_to_dict(properties))
        created = self._post(collection, body).json()
        return created.get("id", 0)

    def addDHCP4RangeBySize(self, networkId, offset, size, properties):
        collection = self._resolve_parent_collection(networkId, "DHCP4Range")
        body = {"type": _v2_type_enum("DHCP4Range"), "range": "%s,%s" % (offset, size)}
        body.update(_v1_props_to_dict(properties))
        created = self._post(collection, body).json()
        return created.get("id", 0)

    def getEntityByRange(self, parentId, address1, address2, type):
        collection = self._resolve_parent_collection(parentId, type)
        result = self._get(collection, filter="range:eq('%s-%s')" % (address1, address2))
        data = result.get("data", [])
        return self._v2_to_v1(data[0] if data else None)

    def getIPRangedByIP(self, containerId, type, address):
        try:
            collection = self._resolve_parent_collection(containerId, type)
        except ValueError:
            collection = "/api/v2/" + self._link_key(type)
        result = self._get(collection, filter="range:contains('%s')" % address)
        data = result.get("data", [])
        return self._v2_to_v1(data[0] if data else None)

    # -----------------------------------------------------------------------------
    # IP addresses / networks
    def getIP4Address(self, containerId, address):
        try:
            collection = self._resolve_parent_collection(containerId, "IP4Address")
        except ValueError:
            collection = "/api/v2/addresses"
        result = self._get(collection, filter="address:'%s'" % address)
        data = result.get("data", [])
        return self._v2_to_v1(data[0] if data else None)

    def getIP4NetworksByHint(self, containerId, start, count, options):
        opts = _v1_props_to_dict(options)
        hint = opts.get("hint", "")
        try:
            collection = self._resolve_parent_collection(containerId, "IP4Network")
        except ValueError:
            collection = "/api/v2/networks"
        filt = "range:startsWith('%s')" % hint if hint else None
        result = self._get(collection, filter=filt, offset=start, limit=count)
        return [self._v2_to_v1(o) for o in result.get("data", [])]

    def changeStateIP4Address(self, addressId, targetState, macAddress):
        ent = self._get_by_id(addressId)
        if not ent:
            raise ValueError("Address id %s not found" % addressId)
        body = {"state": targetState}
        if macAddress:
            body["macAddress"] = macAddress
        self._req("PUT", ent["_links"]["self"]["href"], json=body)
        self._invalidate_entity_cache(addressId)
        return

    def assignIP4Address(self, configurationId, ip4Address, macAddress, hostInfo, action, properties):
        networks = self._get(
            "/api/v2/networks",
            filter="configuration.id:%s and range:contains('%s')" % (configurationId, ip4Address))
        data = networks.get("data", [])
        if not data:
            raise ValueError("No network under configuration %s contains address %s" % (configurationId, ip4Address))
        network = data[0]
        href = network["_links"]["addresses"]["href"]
        body = {"type": _v2_type_enum("IP4Address"), "address": ip4Address, "action": action}
        if macAddress:
            body["macAddress"] = macAddress
        body.update(_v1_props_to_dict(properties))
        created = self._post(href, body).json()
        return created.get("id", 0)

    def assignNextAvailableIP4Address(self, configurationId, parentId, macAddress, hostInfo, action, properties):
        net = self._get_by_id(parentId)
        if not net:
            raise ValueError("Network id %s not found" % parentId)
        href = net.get("_links", {}).get("availableAddresses", {}).get("href")
        if not href:
            raise ValueError("Network id %s has no availableAddresses sub-collection" % parentId)
        candidates = self._get(href, limit=1)
        data = candidates.get("data", [])
        if not data:
            raise ValueError("No available address found under network %s" % parentId)
        address = data[0].get("address")
        return self.assignIP4Address(configurationId, address, macAddress, hostInfo, action, properties)

    # -----------------------------------------------------------------------------
    # MAC addresses / pools
    def getMACAddress(self, configurationId, macAddress):
        collection = self._resolve_parent_collection(configurationId, "MACAddress")
        result = self._get(collection, filter="address:'%s'" % macAddress)
        data = result.get("data", [])
        return self._v2_to_v1(data[0] if data else None)

    def associateMACAddressWithPool(self, configurationId, macAddress, poolId):
        pool = self._get_by_id(poolId)
        if not pool:
            raise ValueError("MAC pool id %s not found" % poolId)
        href = pool.get("_links", {}).get("macAddresses", {}).get("href")
        if not href:
            raise ValueError("MAC pool id %s has no macAddresses sub-collection" % poolId)
        body = {"type": "MACAddress", "address": macAddress}
        return self._post(href, body)

    def denyMACAddress(self, configurationId, macAddress):
        mac_ent = self.getMACAddress(configurationId, macAddress)
        if not mac_ent.get("id"):
            raise ValueError("MAC address %s not found in configuration %s" % (macAddress, configurationId))
        return self._req("PUT", mac_ent["_links"]["self"]["href"], json={"state": "DENIED"})

    # -----------------------------------------------------------------------------
    # generic link/unlink (used for MAC-address-to-pool membership etc.)
    def linkEntities(self, entity1Id, entity2Id, properties):
        ent1 = self._get_by_id(entity1Id)
        ent2 = self._get_by_id(entity2Id)
        if not ent1 or not ent2:
            raise ValueError("Entity not found for linkEntities(%s, %s)" % (entity1Id, entity2Id))
        key = TYPE_LINK_KEY.get(ent2.get("type", ""))
        href = ent1.get("_links", {}).get(key, {}).get("href") if key else None
        if not href:
            raise ValueError("Could not determine relationship to link between %s and %s" % (entity1Id, entity2Id))
        return self._post(href, {"id": entity2Id})

    def unlinkEntities(self, entity1Id, entity2Id, properties=''):
        ent1 = self._get_by_id(entity1Id)
        if not ent1:
            raise ValueError("Entity id %s not found" % entity1Id)
        links = ent1.get("_links", {})
        for key in ("macAddresses", "tags", "users", "servers", "accessRights"):
            href = links.get(key, {}).get("href")
            if not href:
                continue
            try:
                return self._req("DELETE", href.rstrip("/") + "/%s" % entity2Id)
            except ValueError:
                continue
        raise ValueError("Could not determine relationship to unlink between %s and %s" % (entity1Id, entity2Id))

    # -----------------------------------------------------------------------------
    # access rights
    # Fields that are themselves nested JSON objects/arrays on an AccessRight
    # (the resource/user reference, HAL links) - these must NEVER be run
    # through the pipe-delimited properties string. _dict_to_v1_props() only
    # does str(v), so a nested dict comes back as a corrupted Python-repr
    # string (confirmed live: sending that mangled string back on PUT 400'd
    # with JsonDeserializationError) instead of real JSON. Keep them out of
    # 'extra' entirely and always rebuild them fresh from known ids instead.
    _ACCESSRIGHT_OBJECT_FIELDS = ("id", "type", "resource", "entity", "userScope", "user",
                                   "accessOverrides", "overrides", "_links")

    @staticmethod
    def _v1_overrides_to_v2(overrides):
        """v1's 'overrides' was a pipe-delimited string (usually just '|',
        meaning "no per-sub-entity overrides"). CONFIRMED from a live 400
        (JsonDeserializationError): v2 names this field 'accessOverrides'
        and requires an array of AccessRightOverride objects, not a string -
        an empty/']'-only v1 value maps cleanly to an empty list. VERIFY:
        the AccessRightOverride shape for a genuinely populated override
        list isn't confirmed - this is a best-effort guess (one object per
        pipe-separated token, under an 'accessLevel' key) that will need
        checking against Swagger if a script actually uses non-empty
        overrides and this 400s.
        """
        if not overrides or overrides in ("|",):
            return []
        parts = [p for p in overrides.split("|") if p]
        return [{"accessLevel": p} for p in parts]

    @staticmethod
    def _v2_overrides_to_v1(access_overrides):
        """Inverse of _v1_overrides_to_v2() - keeps getAccessRight()'s
        returned ar['overrides'] round-trippable back into
        add/updateAccessRight()'s `overrides` parameter."""
        if not access_overrides:
            return "|"
        return "|".join(str(o.get("accessLevel", o)) for o in access_overrides) + "|"

    def _v2_accessright_to_v1(self, obj):
        """AccessRight is NOT shaped like every other v1 entity (id/name/
        type/properties) - v1's access-right calls returned/expected a dict
        with entityId/userId/value/overrides/properties as direct top-level
        keys instead (access_rights.py does ar['entityId'], ar['value'],
        ar['overrides'], ar['properties'] directly, not via splitProp()).
        Reshape a v2 AccessRight resource into that same v1 shape."""
        if not obj:
            return {"id": 0, "entityId": 0, "userId": 0, "value": None,
                     "overrides": "|", "properties": "", "_links": {}}
        # CONFIRMED from a live 400 (JsonDeserializationError naming the
        # generic entity-type union): the target-entity reference field is
        # "resource", not "entity".
        entity_ref = obj.get("resource") or obj.get("entity") or {}
        # VERIFY: assuming the read side of the relationship is also called
        # "userScope" (confirmed for the create body) rather than "user".
        user_ref = obj.get("userScope") or obj.get("user") or {}
        skip = self._ACCESSRIGHT_OBJECT_FIELDS + ("defaultAccessLevel",)
        extra = {k: v for k, v in obj.items() if k not in skip}
        return {
            "id": obj.get("id", 0),
            "entityId": entity_ref.get("id", 0),
            "userId": user_ref.get("id", 0),
            "value": obj.get("defaultAccessLevel"),
            "overrides": self._v2_overrides_to_v1(obj.get("accessOverrides")),
            "properties": _dict_to_v1_props(extra) if extra else "",
            "_links": obj.get("_links", {}),
        }

    def getAccessRight(self, entityId, userId):
        ent = self._get_by_id(entityId)
        href = ent.get("_links", {}).get("accessRights", {}).get("href") if ent else None
        if not href:
            return self._v2_accessright_to_v1(None)
        # VERIFY: the create body's user/group reference field is confirmed
        # to be "userScope" (not "user") - assuming the same field name
        # applies to filtering this read-only nested collection too; adjust
        # back to "user.id" if this 400s with InvalidFilterField.
        result = self._get(href, filter="userScope.id:%s" % userId)
        data = result.get("data", [])
        return self._v2_accessright_to_v1(data[0] if data else None)

    def getAccessRightsForUser(self, userId, start, count):
        collection = self._resolve_parent_collection(userId, "AccessRight")
        result = self._get(collection, offset=start, limit=count)
        return [self._v2_accessright_to_v1(o) for o in result.get("data", [])]

    def addAccessRight(self, entityId, userId, value, overrides, properties):
        ent = self._get_by_id(entityId)
        if not ent:
            raise ValueError("Entity id %s not found" % entityId)
        # VERIFY (best guess after a live 405 MethodNotAllowed on POSTing to
        # the entity's own nested accessRights link - that link appears to
        # be read-only): access rights aren't part of the generic polymorphic
        # entity hierarchy at all (confirmed separately - "AccessRight" isn't
        # in the root search's 'type' enum), and BlueCat's own release notes
        # mention a dedicated top-level /api/v2/accessRights endpoint - so
        # try POSTing there instead, referencing both the entity and the
        # user/group in the body, rather than nesting under the entity.
        # CONFIRMED from a live 400 (MissingRequiredField): /api/v2/accessRights
        # does require "type", with its own separate enum
        # {AccessRight, AdministrativeAccessRight, FeatureAccessRight} -
        # distinct from (and not present in) the generic entity 'type' enum
        # checked elsewhere. A plain per-object access right is "AccessRight".
        # CONFIRMED from a second live 400: the user/group reference field
        # is named "userScope" (accepting a User or UserGroup reference),
        # not "user".
        # CONFIRMED from a third live 400: the access-level field is named
        # "defaultAccessLevel" (values ADD/CHANGE/FULL/HIDE/VIEW - same
        # vocabulary v1 used), not "value".
        # CONFIRMED from a fourth live 400 (JsonDeserializationError): the
        # target-entity reference field is "resource", not "entity" -
        # "entity" was silently ignored on create (v2 ignores unknown
        # fields), which is why this wasn't caught until update's stricter
        # full-object validation surfaced it.
        # CONFIRMED from a fifth live 400 (JsonDeserializationError): the
        # overrides field is named "accessOverrides" and wants an array of
        # AccessRightOverride objects, not the v1 pipe-delimited string -
        # see _v1_overrides_to_v2().
        body = {
            "type": "AccessRight",
            "resource": {"id": entityId},
            "userScope": {"id": userId},
            "defaultAccessLevel": value,
            "accessOverrides": self._v1_overrides_to_v2(overrides),
        }
        body.update(_v1_props_to_dict(properties))
        try:
            created = self._post("/api/v2/accessRights", body).json()
            return created.get("id", 0)
        except ValueError as e:
            # CONFIRMED from a live 409 (ResourceAlreadyExists): creating an
            # access right for a (entity, user) pair that already has one
            # fails outright rather than upserting. access_rights.py only
            # reaches addAccessRight() when its own lookup
            # (getAllAccessRightsForUser) found no existing match for this
            # entity, so a 409 here means that lookup missed a right that
            # does exist server-side (field-name mismatch is plausible,
            # since getAccessRight()'s read-side field names are still
            # VERIFY, not CONFIRMED, per the comments above). Fall back to
            # updating the existing right in place instead of failing, since
            # that reflects the caller's actual intent (set this access
            # level), whether the right is new or already there.
            if "ResourceAlreadyExists" in str(e) or "already exists" in str(e).lower():
                self.updateAccessRight(entityId, userId, value, overrides, properties)
                existing = self.getAccessRight(entityId, userId)
                return existing.get("id", 0)
            raise

    def updateAccessRight(self, entityId, userId, value, overrides, properties):
        right = self.getAccessRight(entityId, userId)
        if not right.get("id"):
            raise ValueError("Access right not found for entity %s user %s" % (entityId, userId))
        # CONFIRMED from a live 400 (MissingRequiredField): PUT here is a
        # full replace, not a partial patch - it needs every required field
        # (type/entity/userScope/deploymentsAllowed/...), not just the two
        # being changed. Rather than guess every such field one 400 at a
        # time, carry forward whatever this record already had (encoded
        # into right['properties'] by _v2_accessright_to_v1's generic
        # 'extra' handling) and only override defaultAccessLevel/overrides/
        # whatever the caller explicitly passed in `properties`.
        existing_extra = _v1_props_to_dict(right.get("properties"))
        # 'resource'/'entity'/'userScope' must never come from this string -
        # _v2_accessright_to_v1() already keeps them out of 'extra' (see
        # _ACCESSRIGHT_OBJECT_FIELDS), but strip defensively in case an
        # older-shaped 'properties' value is ever passed through here, since
        # a nested object round-tripped through this pipe format comes back
        # as a corrupted string, not real JSON (confirmed live - that's
        # exactly what caused the JsonDeserializationError above).
        for stale_key in self._ACCESSRIGHT_OBJECT_FIELDS:
            existing_extra.pop(stale_key, None)
        # CONFIRMED: 'deploymentsAllowed' wants a real JSON boolean, not the
        # "True"/"False" string splitProp()/joinProp() round-trip produces.
        if "deploymentsAllowed" in existing_extra:
            existing_extra["deploymentsAllowed"] = str(existing_extra["deploymentsAllowed"]).lower() == "true"
        body = {
            "type": "AccessRight",
            "resource": {"id": entityId},
            "userScope": {"id": userId},
        }
        body.update(existing_extra)
        body["defaultAccessLevel"] = value
        body["accessOverrides"] = self._v1_overrides_to_v2(overrides)
        body.update(_v1_props_to_dict(properties))
        self._req("PUT", right["_links"]["self"]["href"], json=body)
        return

    def deleteAccessRight(self, entityId, userId):
        right = self.getAccessRight(entityId, userId)
        if not right.get("id"):
            return
        self._req("DELETE", right["_links"]["self"]["href"])
        return

    # -----------------------------------------------------------------------------
    # server deployment
    # CONFIRMED live (debug_deploy.py/debug_deploy2.py/debug_tftp_deploy3.py):
    # even with type=FullDeployment, the deployments POST still 400s with
    # MissingRequiredField for a separate 'service' field - there is no
    # single "deploy everything" call in v2 like v1 had. The 'service'
    # field's accepted enum values are DYNAMIC, based on what's actually
    # configured/assigned on THAT server - a server with no TFTP group/role
    # assigned only accepts DNS/DHCPv4/DHCPv6 (TFTP 400s InvalidEnumValue),
    # but once a TFTPGroup's TFTPDeploymentRole is assigned to the server,
    # the server's own acceptedValues list grows to include "TFTP" too
    # (confirmed live on dds1 after tftp-group's role was assigned to it).
    # So attempting TFTP here is safe/correct in general - a server without
    # a TFTP role assigned will just 400 for that one service, same as any
    # other inapplicable/disabled service, and (see deployServer() below)
    # that alone doesn't fail the whole full-deploy call.
    _DEPLOY_SERVICES = ("DNS", "DHCPv4", "DHCPv6", "TFTP")
    # v1's coarser "DHCP" (covering v4+v6 together) becomes two calls. Note
    # getServerDeploymentStatus() only ever reports the single
    # most-recently-queued deployment record (see deployServer()'s comment
    # above), so with both queued, the script's status polling will show
    # whichever (DHCPv6) was queued last, not DHCPv4's - by design, per
    # user's explicit request to keep -t dhcp deploying both.
    # DHCPV4/DHCPV6 added per explicit request (deploy_server.py -t now
    # also accepts DHCPv4/DHCPv6 directly, not just the combined "DHCP").
    _SERVICE_TYPE_MAP = {
        "DNS": ["DNS"], "DHCP": ["DHCPv4", "DHCPv6"],
        "DHCPV4": ["DHCPv4"], "DHCPV6": ["DHCPv6"], "TFTP": ["TFTP"],
    }

    def deployServer(self, serverId):
        # v1 "FULL" deploy (no specific service named) = one FullDeployment
        # POST per service this API knows about (see _DEPLOY_SERVICES above).
        errors = []
        for svc in self._DEPLOY_SERVICES:
            try:
                self._post("/api/v2/servers/%s/deployments" % serverId,
                            {"type": "FullDeployment", "service": svc})
            except Exception as e:
                errors.append("%s: %s" % (svc, e))
        if len(errors) == len(self._DEPLOY_SERVICES):
            # every service failed - that's a real failure, not just one
            # inapplicable/disabled service being skipped
            raise ValueError("; ".join(errors))
        return

    def deployServerServices(self, serverId, services):
        svc_key = services.upper() if isinstance(services, str) else None
        svc_list = self._SERVICE_TYPE_MAP.get(svc_key)
        if svc_list is None:
            raise ValueError(
                "BAM v2 shim: unrecognized -t service '%s' (known: DNS, "
                "DHCP, TFTP - v1's 'DHCP' maps to both DHCPv4 and DHCPv6)"
                % services)
        errors = []
        for svc in svc_list:
            try:
                self._post("/api/v2/servers/%s/deployments" % serverId,
                            {"type": "FullDeployment", "service": svc})
            except Exception as e:
                errors.append("%s: %s" % (svc, e))
        if errors:
            raise ValueError("; ".join(errors))
        return

    # CONFIRMED live (deploy_server.py's polling loop 400ed with a KeyError:
    # it does `deploy_rtn_code[rtn]` where deploy_rtn_code's keys are the
    # v1 NUMERIC status code strings "-1".."8" - getServerDeploymentStatus()
    # must return one of those exact strings, not the full deployment
    # record). The v2 deployment resource has TWO separate fields -
    # 'state' (QUEUED/RUNNING/COMPLETED - a coarse lifecycle stage) and
    # 'status' (QUEUED/EXECUTING/DONE - confirmed live via
    # debug_deploy_status.py) - and it's 'status' whose values line up
    # 1:1 with deploy_rtn_code's naming (EXECUTING/QUEUED/DONE), not
    # 'state'. Use 'status', not 'state'. Only QUEUED/EXECUTING/DONE are
    # confirmed live so far; the rest below are best-effort guesses at the
    # natural v2 spelling of the same concept (VERIFY as they're actually
    # observed - e.g. a failed or cancelled deployment).
    _V1_DEPLOY_STATE_CODE = {
        "EXECUTING": "-1",          # CONFIRMED live
        "INITIALIZING": "0",
        "QUEUED": "1",              # CONFIRMED live
        "CANCELLED": "2",
        "FAILED": "3",
        "NOT_DEPLOYED": "4",
        "WARNING": "5",
        "INVALID": "6",
        "DONE": "7",                # CONFIRMED live
        "COMPLETED": "7",           # alternate guess, in case 'status' ever uses this word instead
        "NO_RECENT_DEPLOYMENT": "8",
    }

    def getServerDeploymentStatus(self, serverId, properties):
        result = self._get("/api/v2/servers/%s/deployments" % serverId, orderBy="desc(id)", limit=1)
        data = result.get("data", [])
        if not data:
            return "8"  # NO_RECENT_DEPLOYMENT
        status = (data[0].get("status") or "").upper()
        # unknown/unconfirmed status -> "6" (INVALID), one of the codes the
        # caller's polling loop already treats as "stop checking" rather
        # than looping forever or crashing on an unmapped value; report
        # back what the actual status string was if this ever triggers.
        return self._V1_DEPLOY_STATE_CODE.get(status, "6")

    # -----------------------------------------------------------------------------
    # zone/config path-walking helpers - pure logic, unchanged from v1 (they
    # only call self.getEntityByName()/self.getParent(), which now talk v2).
    def find_zone(self, viewid, zone):
        """given a view id and a zone, return the zone record."""
        ent_json = None
        zones = zone.split(".")
        zoneid = viewid

        while len(zones):
            zone = zones.pop()
            ent_json = self.getEntityByName(zoneid, zone, "Zone")
            zoneid = ent_json['id']
            if zoneid == 0:
                return ent_json
        return ent_json

    def get_zone_id(self, viewid, host):
        """given a view id and a host, get the id of the zone. If it's not a
        zone, return the part that isn't. If the zone doesn't exist, return
        zero as the zone id."""
        zones = host.split(".")
        zoneid = viewid
        parentzone = None
        absolutezone = ""
        leftover = ""

        while len(zones) > 1:
            zone = zones.pop()
            parentzone = zoneid
            response = self.getEntityByName(zoneid, zone + leftover, "Zone")
            newid = response['id']
            if newid:
                zoneid = newid
                absolutezone = zone + "." + absolutezone
            else:
                leftover += "." + zone

        zone = zones.pop() + leftover
        response = self.getEntityByName(zoneid, zone + leftover, "Zone")
        vzone = response['id']
        if vzone:
            zone = ""
            zoneid = vzone
        return (absolutezone, zone, zoneid, parentzone)

    def getConfiguration(self, id):
        while True:
            parent = self.getParent(id)['id']
            if parent == 0:
                return id   # exit func()
            id = parent

    #==========================================================
    # Util - unchanged from v1 (pure string utilities, no API dependency)
    #==========================================================
    def joinProp(self, properties):
        """give a dict made from properties, return a property string"""
        return _dict_to_v1_props(properties)

    def splitProp(self, result):
        properties = result.get('properties')
        if 'properties' not in result or result['properties'] is None:
            properties = ""
        return _v1_props_to_dict(properties)

    def mask_id_pw(self, msg):
        logMsg = re.sub(r"username=.*&password=.*?\s", "username=***&password=***", str(msg))
        return logMsg

# -------------------------------------------------------
# endof class BAM()
# -------------------------------------------------------


# -------------------------------------------------------
# Everything below is unchanged from the v1 BAM.py - pure utility functions
# with no dependency on which Address Manager REST API version is in use.
# -------------------------------------------------------

def get_input_cmd():
    cmdLine = ""
    for x in range(len(sys.argv)):
        if x == 0:
            cmdLine = os.path.splitext(os.path.basename(sys.argv[0]))[0] + ' '
        else:
            if x == (len(sys.argv) - 1):
                cmdLine = cmdLine + sys.argv[x]
            else:
                cmdLine = cmdLine + sys.argv[x] + ' '
    input_cmd_log = f'"," Input: {cmdLine}"'
    return input_cmd_log


class print_log():

    def __init__(self, log_prog_type_index, input_cmd_log, InputlogPath, InputlogFileName):
        self.input_cmd_log = input_cmd_log
        self.log_info_error_index = 0
        self.log_info_error_text = ["INFO", "ERROR"]

        if log_prog_type_index >= 4:
            log_prog_type_index = 4

        self.log_prog_type_text = ["View", "Add", "Delete", "Update", "Other"]
        self.log_prog_type_mag = self.log_prog_type_text[log_prog_type_index]

        self.logger = getLogger(InputlogPath, InputlogFileName)
        self.logger.setLevel(logging.INFO)

    def change_type(self, new_log_prog_type_index):
        self.log_prog_type_mag = self.log_prog_type_text[new_log_prog_type_index]

    def go(self, info_error_index, InputMsg):
        if info_error_index >= 1:
            info_error_index = 1
        info_or_error = self.log_info_error_text[info_error_index]
        logMsg = f'{self.log_prog_type_mag},"[{info_or_error}]:{InputMsg}{self.input_cmd_log}'
        consoleMsg = f'{info_or_error}:{InputMsg}'
        print(consoleMsg)
        self.logger.error(logMsg)

    def log_only(self, info_error_index, InputMsg):
        if info_error_index >= 1:
            info_error_index = 1
        info_or_error = self.log_info_error_text[info_error_index]
        logMsg = f'{self.log_prog_type_mag},"[{info_or_error}]:{InputMsg}{self.input_cmd_log}'
        self.logger.error(logMsg)


def process_password():
    while True:
        print("if you use Python2, please addd quote symoble (') for your input e.g. 'example' )")
        print("   note: the quote symble will not be considered as part of the password")
        password = input("\nLet's type a new password:")
        if password.strip() != "":
            break
    pwd_encrypt = encrypt_password(password)
    print("{0} {1}".format("\nYour password is encrypted as:", pwd_encrypt))
    print("\nPlease update your encrypted password in bamconfig.json file\n")


def encrypt_password(password):
    """Encrypt password with base64"""
    password_bytes = str.encode(password.strip(), encoding='utf-8')
    return base64.b64encode(password_bytes).decode()


def decrypt_password(encoded):
    """Decrypt password with base64"""
    try:
        password_decypt_bytes = base64.b64decode(encoded)
        return password_decypt_bytes.decode('utf-8')
    except Exception as e:
        return ''


def load_config(print_log, configFile):
    log_info = 0
    log_error = 1
    try:
        config = json.load(open(configFile, encoding='utf-8'))
    except Exception as e:
        logMsg = str(e) + ' Configuration file format error.'
        print_log.go(log_error, logMsg)
        return (1)

    configFile_error = False
    configFile_error_msg = ''

    if not 'sshuser' in config:
        configFile_error_msg += ' "sshuser"'
        configFile_error = True
    if not 'hostname' in config:
        configFile_error_msg += ' "hostname"'
        configFile_error = True
    if not 'user' in config:
        configFile_error_msg += ' "user"'
        configFile_error = True
    if not 'password' in config:
        configFile_error_msg += ' "password"'
        configFile_error = True
    if not 'https' in config:
        configFile_error_msg += ' "https"'
        configFile_error = True

    if configFile_error:
        logMsg = "Failure: config file format error%s is required in config file" % (configFile_error_msg)
        print_log.go(log_error, logMsg)
        return (1)

    return config


def bam_logout(bam):
    try:
        response = bam.logout()
        if not response.ok:
            return (1)
        else:
            return (0)
    except Exception as e:
        return (1)


def getHtmlTitle(html_data):
    # Kept for backward compatibility with any script that imports it
    # directly. v2 errors are JSON, not HTML, so this is no longer used
    # internally by this module's own error handling.
    title = ''
    re_result = re.search(r'<\W*title\W*(.*)</title', html_data, re.IGNORECASE)
    if not re_result == None:
        title = re_result.group(1)
    return (title)


def getLogger(InputlogPath, InputlogFileName):
    logPath = None
    fileName = None
    ssh_connection = None
    ssh_client_ip = None
    userid = None

    logPath = InputlogPath
    fileName = InputlogFileName

    if os.name == 'nt':
        ssh_client_ip = ''
    else:
        ssh_connection = os.getenv("SSH_CONNECTION")
        if ssh_connection != None:
            ssh_connection = os.getenv("SSH_CONNECTION").split()
            ssh_client_ip = ssh_connection[0]
        else:
            ssh_client_ip = ''

    userid = getpass.getuser()
    if userid == None:
        userid = ''

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    if HW_project:
        fileHandler = logging.handlers.WatchedFileHandler("{0}vDNS-{1}".format(logPath, fileName))
        formatterString = "%(asctime)s,{0},vDNS,{1},cli,%(message)s".format(userid, ssh_client_ip)
    elif Card_project:
        fileHandler = logging.handlers.WatchedFileHandler("{0}{1}.log".format(logPath, fileName))
        formatterString = "%(asctime)s,{0},bluecat,{1},rpz,%(message)s".format(userid, ssh_client_ip)
    else:
        fileHandler = logging.handlers.WatchedFileHandler("{0}{1}.log".format(logPath, fileName))
        formatterString = "%(asctime)s,{0},bluecat,{1},cli,%(message)s".format(userid, ssh_client_ip)

    logFormatter = logging.Formatter(formatterString, "%Y-%m-%d %H:%M:%S")
    fileHandler.setFormatter(logFormatter)

    if (logger.hasHandlers()):
        logger.handlers.clear()

    logger.addHandler(fileHandler)

    return logger


# ----------------------------------------------------------------------------
# main()
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import doctest
    doctest.testmod()
