#!/usr/bin/python
# coding:utf-8
#
# Copyright 2021 BlueCat Networks. This software is released under an
# OSI-approved license, the Python Software License 2.0. This license is
# incorporated by reference. The license grants you certain rights.
# https://opensource.org/licenses/Python-2.0
#
# Bluecat only provides this Script for reference as a Proof of Concept
#
# by: Eric Chen (hchen@bluecatnetworks.com)
# python ver: python 3
# BAM ver: 26.1
#
# todo:
#  v6.2 20230828 fixed log does not show in cli.py issue 
#  v6.1 update help
#  v6.0 fix TLD (org,gprs, SOS) not print in -y issue. 
#  v5.0 Final Release version (from vt12)
#   vt12 add -m to print man reding format
#        add function to support "-a -n", support print all record with same record name.
#        update cname print error (correct print_rr_type set error)
#   vt11 clean up - delete old remarked prog, add ipaddress to support ipv6 address in host and 4a records
#   vt10 add cname, txt and other new record type to csv2xml csv (append to end).
#        there new records should be skipped by csv2xml
#   vt9 add support -z back due to Huawei's request to query one zone only
#   vt8 add match srv record support (if -r = SRV's host record)
#   vt7 clean up parameters called in recursive_tree() (change recursive to recursive_tree)
#       support handle one view (if "-v view1" is given)
#       Saw BAM timeout problem. Add req_timeout = 180 to wait longer time
#   vt6 save recursive zone id to a list, and walk through zone id list to pring
#   vt5 restructure if logic
#   vt4 ignore case of record name. (convert it to upper case to compare)
# v3.0 20211217 add -n that can filter record name
# v2.0 20211209
# v1.0 20211011 (use BAM.py v20211005-G)
#
# ---------------------------------------------------
# python max recursive calls setting 
# ---------------------------------------------------
# Python's default recursion limit is 1000
# Python won't let a function call on itself more than 1000 times
# the way to overwrite the 1000 is as following
#   import sys
#   x=1500
#   sys.setrecursionlimit(x)
# ---------------------------------------------------

# --- supported record type ---
# HostRecord HostRecord
# AliasRecord AliasRecord
# MXRecord MXRecord
# TXTRecord TXTRecord
# SRVRecord SRVRecord
# HINFORecord HINFORecord       : The Host Info(HINFO) record contains optional text information about a host.
# NAPTRRecord NAPTRRecord
# GenericRecord GenericRecord

# return (0) if error and no record found
# else return number of found record

'''
dump-rr: dump all records in all zones under one view or all views in a configuration

[--- dump RR in one view under a configuration ---]
dump-rr -c config1 -v view1 -a                                # dump all type of records in config1/view1
dump-rr -c config1 -v view1 -t ns                             # dump all NS records
dump-rr -c config1 -v view1 -t ns -n ns1                      # dump all NS with name = ns1
dump-rr -c config1 -v view1 -t ns -r a1.corp                  # dump all NS with rdata = a1.corp
dump-rr -c config1 -v view1 -t ns -r a1.corp -o out.csv -u    # (-o)save to out.csv, (-p)set XML on-exist="update-merge" 
dump-rr -c config1 -v view1 -t ns -r a1.corp -o out.csv -u -p # same as previous, also print output to console (-p)
dump-rr -c config1 -v view1 -z test.corp -t ns                # dump all NS records in config1/view1/test.corp
dump-rr -c config1 -v view1 -t naptr                          # dump all naptr records in config1/view1
dump-rr -c config1 -v view1 -t naptr -n naptr1                # dump all naptr with name=naptr1 in config1/(all views)
dump-rr -c config1 -v view1 -t naptr -r a1.corp               # dump all naptr with replacement = a1.corp 
[--- dump RR in ALL views under a configuration ---]          # when (-v) is not given, all views will be processed.
dump-rr -c config1 -t ns -r a1.corp                           # dump ALL NS with rdata=a1.corp in config1/(all views)
dump-rr -c config1 -y                                          # dump zone list (print all zones in config1)

    -c config_name
    -v view_name
    -z zone_name
    -t rr_type      [host|cname|mx|txt|srv|hinfo|A|AAAA|naptr]
    -n record_name  (print only records' name matches record_name (ignore case))
    -a              (dump all types of records, when -a is used, -t will be ignored)
    -r query        (match rdata = "query" (ignore case))
                     - for NS    :print if rdata = query
                     - for NAPTR :print if replacement = query
                     - for SRV   :print if LinktoHost = query
    -u [d|u]        (set XML update flag (d):"delete" (u):"update-merge")
    -l ttl          (set ttl value)
    -y              (List zone only, don't print record)
    -p              (print output to screen, by default, when use -o, there's no output to screen)
    -m              (Human reading format output instead of CSV format)
    -o out.csv      (save output to "out.csv" file)
    Note: if record is a "same as zone" record, the name field will be empty(no name) in csv output
'''

# ------------- module from internet ---------

import getopt
import sys
import json
import os
import ipaddress

# ------------- module by BlueCat ---------
import BAM


# copy zone_rr_query as local function. Does not use import anymore
# from zone_rr_query import *

# ------------- module from internet ---------
import urllib3  # to suppress https cert worning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------
version = "6.2"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
#sys.tracebacklimit = 0

# set up bam as global var to be access by recursive function. (to Avoid login/logout every time when call recursive fun)
bam=BAM.BAM( "", 3)

recursive_count = 0

req_timeout_set = 60    #set timeout time to 60 sec. to avoid slow BAM response

# recursive() will save found list to here
zone_list = []

# original CSV header (without adding cname, txt )
#header_csv2xml ='OpType,Config,View,ParentZone,ZoneDeployFlag,Name,RecordType,on-exist,TTL,HostAddress,Rdata,naptr-order,naptr-Preference,naptr-Service,naptr-RegExp,naptr-Replacement,naptr-Flags,SRV-Priority,SRV-Weight,SRV-Port,SRV-Host'

# new CSV header that add cname, txt, hinfo (will be ignore by csv2xml)
header_csv2xml ='OpType,Config,View,ParentZone,ZoneDeployFlag,Name,RecordType,on-exist,TTL,HostAddress,Rdata,naptr-order,naptr-Preference,naptr-Service,naptr-RegExp,naptr-Replacement,naptr-Flags,SRV-Priority,SRV-Weight,SRV-Port,SRV-Host,Linkto,Text,HINFO-os,HINFO-cpu,Others'

# (1) OpType, (2)Config, (3)View, (4)ParentZone, (5)ZoneDeployFlag, (6)Name, 
# (7)RecordType, (8)on-exist, (9)TTL, (10) HostAddress, (11)Rdata, (12)naptr-order,
# (13)naptr-Preference, (14)naptr-Service, (15)naptr-RegExp, (16)naptr-Replacement,
# (17)naptr-Flags, (18)SRV-Priority, (19)SRV-Weight, (20)SRV-Port,(21)SRV-Host


#aaaa_csv2xml = '"record","%s","%s",%s,,%s,7"AAAA",8%s,9%s,10,11%s,12,13,14,15,16,17,18,19,20,21'
aaaa_csv2xml = '"record","%s","%s",%s,,%s,"AAAA",%s,%s,,%s,,,,,,,,,,'
a_csv2xml = '"record","%s","%s",%s,,%s,"A",%s,%s,,%s,,,,,,,,,'

#srv_csv2xml = '"record","%s","%s",%s,,%s,7"srv",8%s,9%s,10,11,12,13,14,15,16,17,18%s,19%s,20%s,21%s'
srv_csv2xml = '"record","%s","%s",%s,,%s,"SRV",%s,%s,,,,,,,,,%s,%s,%s,%s'
#(config, view, zone, Record_name, update_flag, ttl, SRV-Priority, SRV-Weight, SRV-Port,SRV-Host)

# note: host has mutiple ip "1.1.0.1,1.1.0.2,1.1.1.3" (need to use double quote to meet CSV requirement)
host_csv2xml = '"record","%s","%s",%s,,%s,"HOST",%s,%s,"%s",,,,,,,,,,'
naptr_csv2xml = '"record","%s","%s",%s,,%s,"NAPTR",%s,%s,,,"%s","%s","%s","%s","%s","%s",,,'
#(config, view, zone, Record_name, update_flag, ttl, order, pref, service, RegEx,replace, flag)

#ns_csv2xml = '1"record",2"%s",3"%s",4%s,5,6%s,7"ns",8%s,9%s,10,11%s,,,,,,,,,,'
ns_csv2xml = '"record","%s","%s",%s,,%s,"NS",%s,%s,,%s,,,,,,,,,,'
#(config, view, zone, Record_name, update_flag, ttl,rdata)

# cname append linkedRecord to end 
cname_csv2xml = '"record","%s","%s",%s,,%s,"CNAME",%s,%s,,,,,,,,,,,,,%s'

# cname append linkedRecord to end 
mx_csv2xml = '"record","%s","%s",%s,,%s,"MX",%s,%s,,,,,,,,,,,,,%s'

# txt append linkedRecord to end 
txt_csv2xml = '"record","%s","%s",%s,,%s,"TXT",%s,%s,,,,,,,,,,,,,,%s'

# txt append linkedRecord to end 
hinfo_csv2xml = '"record","%s","%s",%s,,%s,"HINFO",%s,%s,,,,,,,,,,,,,,,%s,%s'

# other records 
other_csv2xml = '"record","%s","%s",%s,,%s,%s,%s,%s,,,,,,,,,,,,,,,,,"(Warning not all data are printed)"'

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
# def dump_rr(zone_id, rr_type):

def dump_rr(*args):   
    
    global recursive_count
    global zone_list
    
    # convert args to string (for logging)
    passed_args = ''
    for tmp in args:
        passed_args = passed_args + ' '+ tmp 
    
    passed_args = " [Calling arguments]: cname_add " + passed_args
    
    # disable passed_args printing
    passed_args = ''
    
    #print(passed_args)
    
    # ---------------------------------------------------------------------
    # local #def
    # ---------------------------------------------------------------------
    # define log_prog_type_index : to be called in BAM.print_log()
    prog_type_view = 0
    prog_type_add = 1
    prog_type_delete = 2
    prog_type_update = 3
    prog_type_other = 4

    # set log_prog_type_index by script type (view, add, delete etc.) will print eg "view" in log
    log_prog_type_index = prog_type_add

    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    # default = 3 sec. If change any  other number, it will overwrite 
    #       REST requests timeout value
    req_timeout = req_timeout_set

    # read max obj count in API
    max_obj_count = "1000"

    # ---------------------------------------------------------------------
    # local var setup
    # ---------------------------------------------------------------------

    logMsg = ''
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''

    api=''
    apiPw=''
    apiPw_decode = ''
    https=False
    
    configuration = None
    view = None
    zone = None
    rrName = None
    
    rdata = ''
    
    matchclient = None
    user = None
    rrtype = ''
    linkedRecordName = None
    
    update_flag_input = ''  # user input U or D
    update_flag = ''        #default value is "update-merge"
    ttl = ''                # default value is "100"
    
    generic_subtype = ''
    show_version = False
    
    print_flag = False
    print_it = True     # by default, print to screen. Unless -o is set
    
    dump_all = False
    query_name = ''
    
    list_zone_only = False
    output_file = ''
    
    f_out = None
    csv_header = ''
    
    print_csv = True
    
    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    debug_user = False
    debug_api  = False
    debug_bam  = False

    confid = 0
    viewid = 0
    zoneid = 0

    sameAsZone = None
    add_absolutename = None

    # ------ set up program home dir for Win & Linux ------
    workingDir = ''
    logPath = ''
    logFileName = ''
    
    if os.name == 'nt':
        #  same dir in Windows
        workingDir = "./"
        logPath = "./"
        logFileName = "cli"
    else:
        # Linux platform
        workingDir = "./"
        logPath = "/var/log/bluecat/"
        logFileName = "cli"

    # BAM.get_input_cmd() is a function. 
    #----------------------------------------------------------------
    #fixed log input issue when called by cli.py or python3 xxx.py
    #----------------------------------------------------------------
    #get program name. If prog is called by cli.py, then __name__ will be "a_query"
    prog_name = __name__
    
    #convert "_" to "-" in prog_name
    prog_name = prog_name.replace('_','-')
    
    if __name__ == '__main__': #this program is run by python directly (e.g. python3 a_query.py)
         #will get user full input commands and remove ".py"
        input_cmd_log = BAM.get_input_cmd()
    else: #this program is called by cli.py (use args as log output file)
        input_cmd_log_from_args = ' '.join(args)
        input_cmd_log = " Input: %s %s" % (prog_name,input_cmd_log_from_args)
    
    # will create a logger, store input_cmd_log and setup logpath logFileName to logger
    print_log = BAM.print_log( log_prog_type_index ,input_cmd_log, logPath, logFileName)

    # --- load config by BAM.load_config()  return json format "config"
    configFile = workingDir + "bamconfig.json"
    config = BAM.load_config(print_log, configFile)

    if config['https'].upper() == 'TRUE':
        https = True
    else:
        https = False

    # --- get api & apiPw ---
    api = config['user']
    apiPw = config['password'] 
    
    # decode api verify encrypted password to see if it is valid.
    apiPw_decode = BAM.decrypt_password(apiPw) 
        
    if apiPw_decode == '':
        logMsg = "API user password decode error" 
        print_log.go(log_error, logMsg + passed_args)
        return(0)  

    # ---------------------------------------------------------
    # read from CLI
    # ---------------------------------------------------------
    input_args = list(args)   # args is the arguments passed by calling this function.
    try:
        # this is to prepare if this script is called by other python script.
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(  input_args, "dc:v:z:t:an:r:ymu:l:o:ph", ["debug=","version"])           
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:v:z:t:an:r:ymu:l:o:ph", ["debug=","version"])
    except getopt.GetoptError as e: 
        logMsg = str(e) + passed_args
        print_log.go(log_error, logMsg + passed_args)
        return(0) 

    for o,v in opts:
        if o == "-d": debug = True 
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-z": zone = v
        elif o == "-t": rrtype = v
        elif o == "-a": dump_all = True
        elif o == "-n": query_name = v
        elif o == "-r": rdata = v
        elif o == "-y": list_zone_only = True
        elif o == "-m": print_csv = False
        elif o == "-u": update_flag_input = v
        elif o == "-l": ttl = v
        elif o == "-o": output_file = v
        elif o == "-p": print_flag = True
        elif o == "--version": show_version = True
        elif o == "--debug": debug_input = v
        elif o == "-h":
            print (__doc__)
            return(0)

    if not opts:
        print (__doc__)
        return(0)

    if show_version == True:
        print("Version %s" % version)
        return(0)

    # ---------------------------------------------------------
    # debug setup
    # ---------------------------------------------------------
    if debug:
        debug_user = True    # value 1
        debug_api = False 
        debug_bam = False 
    if debug_input == 'api':
        sys.tracebacklimit = 1000   # turn on tracking
        debug_user = True
        debug_api = True 
        debug_bam = False 
    elif debug_input == 'bam':
        sys.tracebacklimit = 1000   # turn on tracking
        debug_user = True
        debug_api = True 
        debug_bam = True 
        
    # ---------------------------------------------------------
    # test cli parameters 
    # ---------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required" 
        print_log.go(log_error, logMsg + passed_args)
        return(0)
        
    if list_zone_only == False:
        if (not dump_all) and (rrtype == ''):
            logMsg = "Failure: -a or -t is required" 
            print_log.go(log_error, logMsg + passed_args)
            return(0)

        target_rrtype = ''
         
        if (not dump_all):
            if rrtype.upper() == "CNAME":
                target_rrtype = "AliasRecord"
            elif rrtype.upper() == "MX":
                target_rrtype = "MXRecord"
            elif rrtype.upper() == "HOST":
                target_rrtype = "HostRecord"
            elif rrtype.upper() == "TXT":
                target_rrtype = "TXTRecord"
            elif rrtype.upper() == "SRV":
                target_rrtype = "SRVRecord"
            elif rrtype.upper() == "NAPTR":
                target_rrtype = "NAPTRRecord"
            elif rrtype.upper() == "HINFO":
                target_rrtype = "HINFORecord"
            elif rrtype.upper() == "A":
                target_rrtype = "GenericRecord"
                generic_subtype = 'A'
            elif rrtype.upper() == "AAAA":
                target_rrtype = "GenericRecord"
                generic_subtype = 'AAAA'
            elif rrtype.upper() == "NS":
                target_rrtype = "GenericRecord"
                generic_subtype = 'NS'
            elif rrtype.upper() == "GENERIC":
                target_rrtype = "GenericRecord"
                generic_subtype = ''
            else:
                target_rrtype = rrtype.upper()
                
                logMsg = "Failure: rrtype %s not supported" % ( rrtype )               
                print_log.go(log_error, logMsg + passed_args)
                return(0)
    
    #endof if list_zone_only == False:
        
    if update_flag_input != '':
        if update_flag_input.upper() == 'D':
            update_flag = 'delete'
        elif update_flag_input.upper() == 'U':
            update_flag = 'update-merge'
        else:    
            update_flag = ''
            print( "Error: -u updage_flag incorrect. Use one of the following options")
            print( "          -u d  (set output XML file's on-exist='delete')" )
            print( "          -u u  (set output XML file's on-exist='update-merge')" )
            return(1)
    else: #of if update_flag_input != '': (means update_flag_input == '', just pass)
        pass
    
    if output_file != '':
        try:
            f_out = open(output_file, 'w')
            
            if print_csv: # if -m is set, don't print csv header to output file
                f_out.write( header_csv2xml + '\n' )
            
            # if file open ok, don't print to screen.
            if print_flag: #if print_flag is set (force print to screen)
                print_it = True
            else:
                print_it = False
            
        except IOError:
            print ("Error: Open file %s error" % output_file)
            if f_out:
                f_out.close()
            return(1)

    
    # ----------------------------------------------------------------
    # login to BAM
    # ----------------------------------------------------------------
    if https:
        BAM_URL = "https://" + config['hostname'] + "/Services/REST/v1/"
    else:
        BAM_URL = "http://" + config['hostname'] + "/Services/REST/v1/"       
    try:                   
        
        #bam=BAM.BAM( BAM_URL, req_timeout)
        
        bam.BAM_URL = BAM_URL
        bam.req_timeout=  req_timeout
        
        response = bam.login( api, apiPw_decode )   #response.ok is checked in bam.login()
    except Exception as e:  # except of login()
        logMsg = bam.mask_id_pw( str(e) )  # mask username and pw in e when login fail
        print_log.go(log_error, logMsg + passed_args)
        return(0)    
    # ----------------------------------------------------------------
    # get config/view/zone
    # ----------------------------------------------------------------
    err_msg = ''
    
    view_list = []
    
    try:
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration) 
                print_log.go(log_error, logMsg + passed_args)
                BAM.bam_logout(bam)
                if f_out:
                    f_out.close()
                return (1)

            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    print_log.go(log_error, logMsg + passed_args)
                    BAM.bam_logout(bam)
                    if f_out:
                        f_out.close()
                    return(1)
                else: #view found. build view_list with only one view (the target view).
                
                    view_list.append([viewid, view]) # view_list will be only ONE view !!
                    
                    if zone:
                        zone_ent = bam.find_zone(viewid, zone)
                        zoneid = zone_ent['id']
                        if zoneid == 0:
                            logMsg = "Failure: Failed to get zone: %s" % (zone)
                            print_log.go(log_error, logMsg)
                            BAM.bam_logout(bam)
                            if f_out:
                                f_out.close()
                            return(1)
                #endof if viewid == 0:
            else:  # of if view: //view name not input, means search all views (igonre -z input)
                if debug_api:
                    print('--- dump all view ---')
                view_ent_Gen = bam.getAllEntities(confid, "View")
                
                for v_ent in view_ent_Gen:  # save view_id and view_name to view_list
                    if debug_api:
                        print (v_ent)
                    view_list.append([v_ent['id'], v_ent['name']])
            #endof if view:
            
            
            # now, view_list[] is all target views that we need to handle. 
            # view_list[] could be one item (if "-v view1" is provided), or all views (if -v is not given )
            # Example:
            #   view_list = [[100893, 'view1'], [100912, 'view2'], [428952, 'view3']]
            
            # --- process view_list[] (one view or all views) ---
            if debug_api:
                print('[debug]: view list to be handled ---')
                print( view_list )
            
            index_id = 0    # used in view_working[] as array index
            index_name = 1  # used in view_working[] as array index
            
            total_recursive_count = 0
            
            #########################################################################
            # Phase I - call recursive to save zone list in global var: zone_list []
            #########################################################################
            
            print('[Phase I - scanning all zones...]')
            
            # view id don't use recursive, use list to scan all items
            for view_working in view_list:
                print("View working...%s" % view_working[index_name])
                # print (view_working[index_id], view_working[index_name])
                
                if zone: # view and zone are all input, means do this zone only
                    # zone_list is a 2-dim array. Ph2 requests for a 2-dim array
                    zone_list.append([view_working[index_name], view_working[index_id], zone, zoneid])
                    
                else: #zone is not input, recursive to get all zones
                    zone_ent_Gen = bam.getAllEntities(view_working[index_id], "Zone")
                
                    for zone_ent in zone_ent_Gen:
                       
                        # Append TLD zone to zone_list before calling recursive_tree()
                        zone_list.append([view_working[index_name], view_working[index_id], zone_ent['name'], zone_ent['id']])
                        

                       #--- call recursive_tree to walk thrhoug all zones and save it to global array zone_list[]
                        recursive_tree(zone_ent['id'], view_working[index_name], view_working[index_id] )
                        
                        if debug_api:
                            print("-----End of call recursive for zone:[%s] recursive:%s ---" % 
                                    (zone_ent['name'], recursive_count) )
                            
                        #print ('recursive times:%s' % recursive_count)
                        total_recursive_count = total_recursive_count + recursive_count
                        recursive_count = 0
                    
                    #endof for zone_ent in zone_ent_Gen:
            #endof for view_working in view_list:
            
            
            #######################################################
            # Phase II - recursive result is saved in global zone_list []
            #######################################################
            
            total_zone = len(zone_list)
            
            print('[Phase 2 - Total %s zones found. Scanning all zones...]' % total_zone)
            
            print_count = 0
            worked_zone = 1
            
            for w_zone in zone_list:    # w_zone means working zone. 
                # w_zone[0] = ['view1', 100893, 'test.corp', 100896]
                    
                if list_zone_only:
                    msg ='%s,%s,%s' % (configuration,w_zone[0], w_zone[2])
                    print( msg )
                    if f_out:
                        try:
                            f_out.write(msg+'\n')
                        except IOError:
                            print ("Error: Open file %s error" % output_file)
                            if f_out:
                                f_out.close()
                            return(1)
                else:
                    #msg ='[%s,%s,%s]' % (configuration, w_zone[0], w_zone[2])
                    #print( 'working zone: %s  %s/%s' % (msg, worked_zone,total_zone,) )
                    
                    if dump_all:
                        all_flag = '-a'
                    else:
                        all_flag = ''
                    
                    print_count = zone_rr_query( '-c', configuration, '-f', w_zone[0], '-z', w_zone[2] ,
                        all_flag, '-t', rrtype, rdata, f_out, print_it, update_flag, ttl, query_name, print_csv)  
                          
                    msg ='[%s,%s,%s]' % (configuration, w_zone[0], w_zone[2])
                    print( '- working zone: %s done!  %s/%s (records %s)' % (msg, worked_zone,total_zone, print_count) )
                          
                worked_zone += 1
            #endof for w_zone in zone_list:
            if debug_api:
                print ('Total recursive times:%s' % total_recursive_count)
        #endof if configuration:
        BAM.bam_logout(bam)
        if f_out:
            f_out.close()
        return (0)
        
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg + passed_args)
        BAM.bam_logout(bam) 
        if f_out:
            f_out.close()
        return (0)

    if output_file != '':
        try:
            if f_out:
                f_out.close()
        except ValueError as e:
            logMsg = "%s" % ( str(e) )
            #print_log.go(log_error, logMsg + passed_args)
            print(logMsg)
            print ("Error: Open file %s error" % output_file)
            if f_out:
                f_out.close()
            return(1)

    #################################################################################
    # End of dump_rr
    #################################################################################

#----------------------------------------------------------------------
# recursive_tree()
#   walk thrhoug all zones and save it to global array zone_list[]. 
#   view_name is only used to save the view name to global zone_list
#----------------------------------------------------------------------
def recursive_tree( parent_zone_id, view_name, view_id ):

    global bam  # should we pass BAM to this function? will it be create multiple times when doing recursive?
                # it seems that using global var can avoid it?
                
    global recursive_count  # to see how many recursive has been run
    global zone_list    #save all zones to global zone_list[]
    
    recursive_count = recursive_count + 1
    
    zone_ent_gen = bam.getAllEntities(parent_zone_id, "Zone")
    for zone_ent in zone_ent_gen:
        
        zone_prop = bam.splitProp(zone_ent)
        zone_name = zone_ent['name']
        zone_absoluteName = zone_prop['absoluteName']
                
        zone_list.append( [view_name, view_id, zone_absoluteName, zone_ent['id'] ] )
        recursive_tree(zone_ent['id'], view_name, view_id)
    return 

##########################################################################
# zone_rr_query (not use import .py file. put function here to avoid
#   login BAM multiple times when every time call this func()
##########################################################################
def zone_rr_query(confg_flag, config_name, view_flag, view_name, zone_flag, zone_absoluteName ,
            all_flag, type_flag, rr_type, rdata, f_out, print_it, update_flag, ttl,query_name, print_csv):   
    
    global req_timeout_set
    
    # ---------------------------------------------------------------------
    # local #def
    # ---------------------------------------------------------------------
    # define log_prog_type_index : to be called in BAM.print_log()
    prog_type_view = 0
    prog_type_add = 1
    prog_type_delete = 2
    prog_type_update = 3
    prog_type_other = 4

    # set log_prog_type_index by script type (view, add, delete etc.) will print eg "view" in log
    log_prog_type_index = prog_type_add

    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    # default = 3 sec. If change any  other number, it will overwrite 
    #       REST requests timeout value
    req_timeout = req_timeout_set

    # read max obj count in API
    max_obj_count = "1000"

    # ---------------------------------------------------------------------
    # local var setup
    # ---------------------------------------------------------------------
    logMsg = ''
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''

    api=''
    apiPw=''
    apiPw_decode = ''
    https=False
    
    configuration = None
    view = None
    zone = None
    rrName = None
    
    
    matchclient = None
    user = None
    linkedRecordName = None
    
    generic_subtype = ''
    

    show_version = False
    
    dump_all = False
    print_rr_type = ''
    print_go = False
    print_count = 0
    
    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    debug_user = False
    debug_api  = False
    debug_bam  = False

    confid = 0
    viewid = 0
    zoneid = 0

    sameAsZone = None
    add_absolutename = None

    
    # ---------------------------------------------------------
    # use the following configuration, view, zone to print
    # ---------------------------------------------------------
    configuration = config_name
    view = view_name
    zone = zone_absoluteName
    
    
    if all_flag == '-a':
        dump_all = True
    else:
        dump_all = False
    
    
    if dump_all:
        rrtype = ''
    else:
        rrtype = rr_type
    
    # ---------------------------------------------------------
    # test cli parameters 
    # ---------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required" 
        #print_log.go(log_error, logMsg + passed_args)
        return(0)

    if (not view) or (view[0:1] == "-"):
        logMsg = "Failure: -v view option is required" 
        #print_log.go(log_error, logMsg + passed_args)
        return(0)

    if (not zone) or (zone[0:1] == "-"): 
        logMsg = "Failure: -z zone option is required" 
        #print_log.go(log_error, logMsg + passed_args)
        return(0)


    if (not dump_all) and (rrtype == ''):
        logMsg = "Failure: -a or -t is required" 
        #print_log.go(log_error, logMsg + passed_args)
        return(0)

    target_rrtype = ''
     
    if (not dump_all):
        if rrtype.upper() == "CNAME":
            target_rrtype = "AliasRecord"
        elif rrtype.upper() == "MX":
            target_rrtype = "MXRecord"
        elif rrtype.upper() == "HOST":
            target_rrtype = "HostRecord"
        elif rrtype.upper() == "TXT":
            target_rrtype = "TXTRecord"
        elif rrtype.upper() == "SRV":
            target_rrtype = "SRVRecord"
        elif rrtype.upper() == "NAPTR":
            target_rrtype = "NAPTRRecord"
        elif rrtype.upper() == "HINFO":
            target_rrtype = "HINFORecord"
        elif rrtype.upper() == "A":
            target_rrtype = "GenericRecord"
            generic_subtype = 'A'
        elif rrtype.upper() == "AAAA":
            target_rrtype = "GenericRecord"
            generic_subtype = 'AAAA'
        elif rrtype.upper() == "NS":
            target_rrtype = "GenericRecord"
            generic_subtype = 'NS'
        elif rrtype.upper() == "GENERIC":
            target_rrtype = "GenericRecord"
            generic_subtype = ''
        else:
            logMsg = "Failure: rrtype %s error" % ( rrtype )               
            #print_log.go(log_error, logMsg + passed_args)
            
            #print(logMsg)
            return(0)

    # ----------------------------------------------------------------
    # get config/view/zone
    # ----------------------------------------------------------------
    err_msg = ''
    try:
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration) 
                #print_log.go(log_error, logMsg + passed_args)
                return (0)

            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    #print_log.go(log_error, logMsg + passed_args)
                    return(0)

                if zone:
                    zone_ent = bam.find_zone(viewid, zone)
                    zoneid = zone_ent['id']
                    if zoneid == 0:
                        logMsg = "Failure: Failed to get zone: %s" % (zone)  
                        #print_log.go(log_error, logMsg + passed_args)
                        return(0)
                    # ------------------------------------------------ 
                    # End of read config/view/zone 
                    # ------------------------------------------------ 

                    # ============================================================================= 
                    # if dump all : // getAllEntities() get all type of RR from list rr_type
                    # =============================================================================
                     
                    if dump_all:
                        rr_type = ['HostRecord', 'AliasRecord' , 'MXRecord', 'TXTRecord',  'SRVRecord',  'HINFORecord',  
                                   'NAPTRRecord',  'GenericRecord']
                        rr_count = 0
                        rr_count_item = 0
                        
                        for rr_type_item in rr_type:
                            try:
                                rtn = bam.getAllEntities( zoneid, rr_type_item)
                            except ValueError as e:
                                logMsg = "Failure: %s Failed to dump zone %s record" % ( str(e), zone)
                                        
                                #print_log.go(log_error, logMsg + passed_args)
                                print(log_error, logMsg)
                                
                                # eric to change
                                
                                print(logMsg)
                                
                                return (0)
                            
                            rr_count_item = 0
                            
                            
                            print_go = False
                            
                            for item in rtn:
                                # print RR with different format (for different RR TYPE)
                                
                                # change "same as zone name"
                                Name_sameASzone_str = ''
                                if item['name'] == '':
                                    #Name_sameASzone_str = '(Same as Zone)'
                                    
                                    # to meet csv2xml format, the "name" of SameAszone record need to be ''
                                    Name_sameASzone_str = ''
                                    
                                else:
                                    Name_sameASzone_str = item['name'] 
                                properties = bam.splitProp(item)
                                
                                
                                # -------------------------------------------------    
                                if item['type'] == "HostRecord":
                                    print_rr_type = 'HostRecord'
                                    
                                    if query_name == '':
                                        print_go = True
                                    else: #of if query_name == '': # mean print only match RR
                                        if item['name'].upper() == query_name.upper():
                                                print_go = True
                                    #endof if query_name == '': # mean print all
                                    
                                    if print_csv:
                                        printStr = host_csv2xml % ( configuration, view, zone, Name_sameASzone_str,  
                                            update_flag, ttl, properties['addresses']  )
                                    else:
                                        printStr = "%s, %s, %s, Record Type:%s PTR:%s Name:%s IP:%s" % (configuration, view,
                                            zone, 'Host', properties['reverseRecord'], Name_sameASzone_str, 
                                            properties['addresses']  )
                                    
                                # -------------------------------------------------    
                                elif item['type'] == "AliasRecord":
                                    print_rr_type = 'AliasRecord'
                                    
                                    if query_name == '':
                                        print_go = True
                                    else: #of if query_name == '': # mean print only match RR
                                        if item['name'].upper() == query_name.upper():
                                                print_go = True
                                    #endof if query_name == '': # mean print all
                                    
                                    if print_csv:
                                        printStr = cname_csv2xml % ( configuration, view, zone, Name_sameASzone_str,  
                                            update_flag, ttl, properties['linkedRecordName']  )
                                    else:
                                        printStr = "%s, %s, %s, Record Type:%s Name:%s LinkedRecordName:%s" % (configuration, 
                                            view, zone, 'CNAME', Name_sameASzone_str, properties['linkedRecordName']  )
                                    
                                # -------------------------------------------------    
                                elif item['type'] == "MXRecord":
                                    print_rr_type = 'MXRecord'                                
                                
                                
                                    if query_name == '':
                                        print_go = True
                                    else: #of if query_name == '': # mean print only match RR
                                        if item['name'].upper() == query_name.upper():
                                                print_go = True
                                    #endof if query_name == '': # mean print all

                                    if print_csv:
                                        printStr = mx_csv2xml % ( configuration, view, zone, Name_sameASzone_str,  
                                            update_flag, ttl, properties['linkedRecordName']  )
                                    else:
                                        printStr = "%s, %s, %s, Record Type:%s Name:%s LinkedRecordName:%s" % (configuration,
                                            view, zone, 'MX', Name_sameASzone_str, properties['linkedRecordName']  )
                                    
                                # -------------------------------------------------    
                                elif item['type'] == "TXTRecord":
                                    print_rr_type = 'TXTRecord'                                
                                
                                    #printStr = "%s, %s, Record Type:%s Name:%s inkedRecordName:%s" % (view, zone, 'TXT', 
                                    #    Name_sameASzone_str, properties['txt']  )
                                    
                                    
                                    if query_name == '':
                                        print_go = True
                                    else: #of if query_name == '': # mean print only match RR
                                        if item['name'].upper() == query_name.upper():
                                                print_go = True
                                    #endof if query_name == '': # mean print all
                                    if print_csv:
                                        printStr = txt_csv2xml % ( configuration, view, zone, Name_sameASzone_str,  
                                            update_flag, ttl, properties['txt']  )
                                    else:
                                        printStr = "%s, %s, %s, Record Type:%s Name:%s TXT:%s" % (configuration,
                                            view, zone, 'TXT', Name_sameASzone_str, properties['txt']   )
                                # -------------------------------------------------    
                                elif item['type'] == "SRVRecord":
                                    print_rr_type = 'SRVRecord'        
                                    
                                    if query_name == '':
                                        print_go = True
                                    else: #of if query_name == '': # mean print only match RR
                                        if item['name'].upper() == query_name.upper():
                                                print_go = True
                                    #endof if query_name == '': # mean print all

                                    if print_csv:
                                        printStr = srv_csv2xml % ( configuration, view, zone, Name_sameASzone_str, 
                                            update_flag, ttl, properties['priority'], properties['weight'], 
                                            properties['port'], properties['linkedRecordName'] )
                                    else:
                                        printStr = ( "%s, %s, %s, Record Type:%s Name:%s port:%s priority:%s" 
                                                      " weight:%s linkedRecordName:%s" ) % ( configuration,
                                                       view, zone, 'SRV', Name_sameASzone_str,
                                                       properties['port'], properties['priority'], properties['weight'], 
                                                       properties['linkedRecordName']   
                                                     )
                                # -------------------------------------------------    
                                elif item['type'] == "HINFORecord":
                                    print_rr_type = 'HINFORecord'                                
                                
                                    if query_name == '':
                                        print_go = True
                                    else: #of if query_name == '': # mean print only match RR
                                        if item['name'].upper() == query_name.upper():
                                                print_go = True
                                    #endof if query_name == '': # mean print all
                                
                                    if print_csv:
                                        printStr = hinfo_csv2xml % ( configuration, view, zone, Name_sameASzone_str, 
                                            update_flag, ttl, properties['os'], properties['cpu'] )
                                    else:
                                        printStr = "%s, %s, %s, Record Type:%s Name:%s os:%s cpu:%s" % ( configuration, 
                                            view, zone, 'HINFO', Name_sameASzone_str, properties['os'], 
                                            properties['cpu'])
                                # -------------------------------------------------    
                                elif item['type'] == "NAPTRRecord":
                                    print_rr_type = 'NAPTRRecord'     
                                                               
                                    if query_name == '':
                                        print_go = True
                                    else: #of if query_name == '': # mean print only match RR
                                        if item['name'].upper() == query_name.upper():
                                                print_go = True
                                    #endof if query_name == '': # mean print all
                                                               
                                    if print_csv:
                                        printStr = naptr_csv2xml % (configuration, view, zone, Name_sameASzone_str, 
                                                update_flag, ttl, properties['order'], properties['preference'], 
                                                properties['service'], properties['regexp'], properties['replacement'],
                                                properties['flags']  )
                                    else:
                                    
                                        printStr = "%s, %s, %s, Record Type:%s Name:%s order:%s preference:%s service:%s regexp:%s replacement:%s flags:%s" % ( 
                                           configuration, view, zone, 'NAPTR', Name_sameASzone_str,
                                           properties['order'], 
                                           properties['preference'], 
                                           properties['service'], 
                                           properties['regexp'],
                                           properties['replacement'],
                                           properties['flags'],
                                         )
                                    
                                # -------------------------------------------------    
                                elif item['type'] == "GenericRecord":


                                    #################################################
                                    # handle all RR within Generic
                                    #################################################
                                    
                                    if properties['type']=='A':
                                        
                                        if query_name == '':
                                            print_go = True
                                        else: #of if query_name == '': # mean print only match RR
                                            if item['name'].upper() == query_name.upper():
                                                    print_go = True
                                        #endof if query_name == '': # mean print all
                                
                                        if print_csv:
                                            printStr = a_csv2xml % (configuration, view, zone, Name_sameASzone_str, 
                                                update_flag, ttl, properties['rdata'] )
                                        else:
                                            printStr = "%s, %s, %s, Record Type:%s Name:%s Rdata:%s" % ( configuration,
                                                view, zone, properties['type'], Name_sameASzone_str, 
                                                properties['rdata']  )
                                    #----------------------------------------------                             
                                    elif properties['type']=='AAAA':
                                        
                                        if query_name == '':
                                            print_go = True
                                        else: #of if query_name == '': # mean print only match RR
                                            if item['name'].upper() == query_name.upper():
                                                    print_go = True
                                        #endof if query_name == '': # mean print all
                                        
                                        if print_csv:
                                            printStr = aaaa_csv2xml % (configuration, view, zone, Name_sameASzone_str, 
                                                        update_flag, ttl, properties['rdata'] )
                                        else:
                                            printStr = "%s, %s, %s, Record Type:%s Name:%s Rdata:%s" % ( configuration,
                                                view, zone, 'AAAA', Name_sameASzone_str, 
                                                properties['rdata']  )
                                    #----------------------------------------------                             
                                    elif properties['type']=='NS':

                                        if query_name == '':
                                            print_go = True
                                        else: #of if query_name == '': # mean print only match RR
                                            if item['name'].upper() == query_name.upper():
                                                    print_go = True
                                        #endof if query_name == '': # mean print all

                                        if print_csv:
                                            printStr = ns_csv2xml % (configuration, view, zone, Name_sameASzone_str, 
                                                update_flag, ttl, properties['rdata'] )
                                        else:
                                            printStr = "%s, %s, %s, Record Type:%s Name:%s Rdata:%s" % (
                                                configuration, view, zone, 'NS', Name_sameASzone_str, 
                                                properties['rdata']  )
                                                              
                                    else:    # not match any type ablve
                                        
                                        #other_csv2xml = '"record","%s","%s",%s,,%s,%s,%s,%s,,,,,,,,,,,,,,'

                                        if query_name == '':
                                            print_go = True
                                        else: #of if query_name == '': # mean print only match RR
                                            if item['name'].upper() == query_name.upper():
                                                    print_go = True
                                        #endof if query_name == '': # mean print all
                                        if print_csv:
                                            printStr = other_csv2xml % ( configuration, view, zone, 
                                                    Name_sameASzone_str, properties['type'], update_flag, ttl)
                                        else:
                                            printStr = "%s, %s, %s, Record Type:%s Name:%s Rdata:%s" % (
                                                configuration, view, zone, properties['type'], Name_sameASzone_str, 
                                                properties['rdata']  )

                                    #ndof if properties['type']=='A':
                                    #-------------------------------------------------
                                    
                                else: # of if item['type'] == "HostRecord":
                                    if query_name == '':
                                        print_go = True
                                    else: #of if query_name == '': # mean print only match RR
                                        if item['name'].upper() == query_name.upper():
                                                print_go = True
                                    #endof if query_name == '': # mean print all

                                    # in case thre's RR type not handled previously, ths should not happen
                                    print("Warning: Record unknown, not print to file")
                                    print(item)
                                    
                                #endof if item['type'] == "HostRecord":
                                #--------------------------------------------------------------------------
                            
                                rr_count_item = rr_count_item + 1
                                
                                if print_go:
                                    if print_it:
                                        print( printStr )
                                        print_count = print_count + 1   # for both print_it or f_out, need to ++
                                        
                                    if f_out:   # write to file
                                        try:
                                            f_out.write( printStr + '\n' )
                                        except IOError:
                                            print ("Error: Open file %s error" % output_file)
                                            if f_out:
                                                f_out.close()
                                            return(1)
                                        print_count = print_count + 1   # for both print_it or f_out, need to ++
                                    #endif f_out:   # write to file
                                    
                                    rr_count = rr_count + 1
                                    
                                #endof if print_go:
                                
                                print_go = False
                            #endof for item in rtn:
                            
                            rr_count = rr_count + rr_count_item
                            
                        # endof for rr_type_item in rr_type:
                        if debug_api:
                            print( "total: %s" % rr_count)
                        
                        # the final value is rr_count
                    
                    #-------------------------------------------------------------
                    # not dump all // getAllEntities() only get target RR_type
                    #-------------------------------------------------------------
                    else: #of if dump_all: # not dump all, only dump a type of record
                        
                        try:
                            rtn = bam.getAllEntities( zoneid, target_rrtype)
                        except ValueError as e:
                            logMsg = "Failure: %s Failed to dump zone %s record" % ( str(e), zone)
                                    
                            p#rint_log.go(log_error, logMsg + passed_args)
                            print(log_error, logMsg + passed_args)
                            return (0)

                        rr_count = 0
                        print_count = 0
                        
                        # -------------------------------------------------------
                        # loop through all RR
                        # -------------------------------------------------------
                        for item in rtn:
                        
                            # --- for debug only ---
                            # print('[debog]------------')
                            # print(item)

                            print_go = False
                            print_rr_type = ''

                            Name_sameASzone_str = ''
                            if item['name'] == '':

                                #to meet csv2xml requirement, the "name" of SameAszone record need to be ''
                                
                                #Name_sameASzone_str = '(Same as Zone)'                                
                                Name_sameASzone_str = ''
                                
                            else:
                                Name_sameASzone_str = item['name'] 
                            properties = bam.splitProp(item)
                            
                            #----------------------------------------------------    
                            if item['type'] == "HostRecord":
                                print_rr_type = 'HostRecord'
                                
                                #print(properties)
                                
                                if query_name == '': # means print all
                                    if rdata == '':     # rdata is not provided. Means print all 
                                        print_go = True
                                        
                                    else: # print only match rdata record (match replacement)
                                    
                                        # if host has IPv6 address, need to use ipaddress.ip_address() to check
                                        address_list = properties['addresses'].split(',')
                                        
                                        for addr in address_list:
                                            if ipaddress.ip_address(rdata) == ipaddress.ip_address(addr):
                                                print_go = True
                                            
                                else: #of if query_name == '': # means print only match RR
                                    if item['name'].upper() == query_name.upper():
                                        print_go = True                                    

                                #endof if query_name == '': # mean print all
                                        
                            #----------------------------------------------------    
                            elif item['type'] == "AliasRecord":
                                print_rr_type = 'AliasRecord'
                                
                                if query_name == '': # mean print all
                                    if rdata == '':     # rdata is not provided. Means print all 
                                        print_go = True                                    
                                    else: # print only match rdata record (match replacement)
                                        if rdata.upper() == properties['linkedRecordName'].upper():
                                            print_go = True
                                else: #of if query_name == '': # mean print only match RR
                                    if item['name'].upper() == query_name.upper():
                                        print_go = True
                                #endof if query_name == '': # mean print all
                                        
                            #----------------------------------------------------    
                            elif item['type'] == "MXRecord":
                                print_rr_type = 'MXRecord'
                                
                                if query_name == '': # mean print all
                                    if rdata == '':     # rdata is not provided. Means print all 
                                        print_go = True                                    
                                    else: # print only match rdata record (match replacement)
                                        if rdata.upper() == properties['linkedRecordName'].upper():
                                            print_go = True
                                else: #of if query_name == '': # mean print only match RR
                                    if item['name'].upper() == query_name.upper():
                                        print_go = True                                    
                                #endof if query_name == '': # mean print all
                                        
                            #----------------------------------------------------    
                            elif item['type'] == "TXTRecord":
                                print_rr_type = 'TXTRecord'
                                if query_name == '': # mean print all
                                    if rdata == '':     # rdata is not provided. Means print all 
                                        print_go = True                                    
                                    else: # print only match rdata record (match replacement)
                                        if rdata.upper() == properties['txt'].upper():
                                            print_go = True
                                else: #of if query_name == '': # mean print only match RR
                                    if item['name'].upper() == query_name.upper():
                                        print_go = True                                    
                                #endof if query_name == '': # mean print all
                            #----------------------------------------------------    
                            elif item['type'] == "SRVRecord":
                                print_rr_type = 'SRVRecord'
                                if query_name == '': # mean print all
                                    if rdata == '':     # rdata is not provided. Means print all 
                                        print_go = True                                    
                                    else: # print only match rdata record (match link_host_record)
                                        if rdata.upper() == properties['linkedRecordName'].upper():
                                            print_go = True
                                else: #of if query_name == '': # mean print only match RR
                                    if item['name'].upper() == query_name.upper():
                                        print_go = True                                    
                                    else:
                                        #not match (not print)
                                        pass
                                #endof if query_name == '': # mean print all
                                
                            #----------------------------------------------------    
                            elif item['type'] == "HINFORecord":
                                print_rr_type = 'HINFORecord'
                                
                                if query_name == '': # mean print all
                                    if rdata == '':     # rdata is not provided. Means print all 
                                        print_go = True                                    
                                    
                                    # --- don't check other condition (e.g. rdata)
                                    #else: # print only match rdata record (match replacement)
                                    #    if rdata.upper() == properties['replacement'].upper():
                                    #        print_go = True
                                
                                else: #of if query_name == '': # mean print only match RR
                                                                
                                    if item['name'].upper() == query_name.upper():
                                        print_go = True                                    
                                    else:
                                        #not match (not print)
                                        pass
                                #endof if query_name == '': # mean print all
                                
                            #----------------------------------------------------    
                            elif item['type'] == "NAPTRRecord":
                                print_rr_type = 'NAPTRRecord'
                                
                                if query_name == '': # mean print all
                                    if rdata == '':     # rdata is not provided. Means print all 
                                        print_go = True                                    
                                    else: # print only match rdata record (match replacement)
                                        if rdata.upper() == properties['replacement'].upper():
                                            print_go = True
                                else: #of if query_name == '': # mean print only match RR
                                    if item['name'].upper() == query_name.upper():
                                        print_go = True                                    
                                    else:
                                        #not match (not print)
                                        pass
                                #endof if query_name == '': # mean print all

                            #----------------------------------------------------    
                            elif item['type'] == "GenericRecord":
                            
                                # for all GenericRecord, need to check if properties['type']=='XXX':
                                #----------------------------------------------------    
                                if generic_subtype == 'A':  
                                    
                                    if properties['type']=='A':
                                        print_rr_type = 'A'

                                        if query_name == '': # mean print all
                                            if rdata == '':     # rdata is not provided. Means print all 
                                                print_go = True                                    
                                            else: # print only match rdata record (match replacement)
                                                if rdata.upper() == properties['rdata'].upper():
                                                    print_go = True
                                        else: #of if query_name == '': # mean print only match RR
                                            if item['name'].upper() == query_name.upper():
                                                print_go = True                                    
                                        #endof if query_name == '': # mean print all
                                        
                                #----------------------------------------------------    
                                elif generic_subtype == 'AAAA': 
                                
                                    if properties['type']=='AAAA':
                                        print_rr_type = 'AAAA'
                                        
                                        if query_name == '': # mean print all
                                            if rdata == '':     # rdata is not provided. Means print all 
                                                print_go = True                                    
                                                
                                            else: # print only match rdata record (match replacement)
                                            
                                                # for IPv6 addr, need to use ipaddress() to check
                                                try: # if input ipv6 format error, except will be run
                                                     # ValueError: 'data' does not appear to be an IPv4 or IPv6 address
                                                    if ipaddress.ip_address(rdata) == ipaddress.ip_address(properties['rdata']):
                                                        print_go = True
                                                except ValueError as e:
                                                    logMsg = "Failure: "+ str(e)
                                                    # print_log.go(log_error, logMsg)
                                                    print(logMsg)
                                                    return(1)
                                        
                                        else: #of if query_name == '': # mean print only match RR
                                            if item['name'].upper() == query_name.upper():
                                                print_go = True                                    
                                        #endof if query_name == '': # mean print all
                                        
                                #-------------------------------------------------------
                                elif generic_subtype == 'NS':
                                    if properties['type']=='NS':
                                        print_rr_type = 'NS'
                                        
                                        if query_name == '': # mean print all
                                            if rdata == '':     # rdata is not provided. Means print all 
                                                print_go = True                                    
                                            else: # print only match rdata record (match replacement)
                                                if rdata.upper() == properties['rdata'].upper():
                                                    print_go = True
                                        else: #of if query_name == '': # mean print only match RR
                                            if item['name'].upper() == query_name.upper():
                                                print_go = True                                    
                                        #endof if query_name == '': # mean print all
                                        
                                #-------------------------------------------------------
                                else: #of if generic_subtype == 'A':   # mean others

                                    #printStr = " %s, %s, Record Type:%s Name:%s Rdata:%s" % ( view, zone,
                                    #    properties['type'], Name_sameASzone_str, properties['rdata']  )
                                    
                                    printStr = other_csv2xml % ( configuration, view, zone, 
                                            Name_sameASzone_str, properties['type'], update_flag, ttl)

                            else: # of if item['type'] == "HostRecord":
                                # in case thre's RR type not handled previously. 
                                
                                print("Warning: Record unknown, not print to file")
                                print(item)
                                
                                print_count = print_count + 1
                                
                            #endof if item['type'] == "HostRecord":
                            
                            # ------------------------------------------
                            #  Every RR will loop through here
                            # ------------------------------------------
                            
                            # build printStr according to record type
                            if print_rr_type == 'NS':
                                if print_csv:
                                    printStr = ns_csv2xml % (configuration, view, zone, Name_sameASzone_str, 
                                        update_flag, ttl, properties['rdata'] )
                                else:
                                    printStr = "%s, %s, %s, Record Type:%s Name:%s Rdata:%s" % (
                                        configuration, view, zone, 'NS', Name_sameASzone_str, 
                                        properties['rdata']  )
                    
                            elif print_rr_type == 'NAPTRRecord':
                            
                                if print_csv:
                                    printStr = naptr_csv2xml % (configuration, view, zone, 
                                            Name_sameASzone_str, update_flag, ttl, 
                                            properties['order'], properties['preference'], properties['service'],
                                            properties['regexp'], properties['replacement'],properties['flags']    )
                                else:
                                    printStr = "%s, %s, %s, Record Type:%s Name:%s order:%s preference:%s service:%s regexp:%s replacement:%s flags:%s" % ( 
                                       configuration, view, zone, 'NAPTR', Name_sameASzone_str,
                                       properties['order'], 
                                       properties['preference'], 
                                       properties['service'], 
                                       properties['regexp'],
                                       properties['replacement'],
                                       properties['flags'],
                                     )
                            
                            elif print_rr_type == 'HostRecord':
                                    
                                if print_csv:
                                    # host_csv2xml = '"record","%s","%s",%s,,%s,"host",%s,%s,%s,,,,,,,,,,'
                                    printStr = host_csv2xml % ( configuration, view, zone, Name_sameASzone_str, 
                                        update_flag, ttl, properties['addresses']  )
                                else:
                                    printStr = "%s, %s, %s, Record Type:%s PTR:%s Name:%s IP:%s" % (configuration, view,
                                        zone, 'Host', properties['reverseRecord'], Name_sameASzone_str, 
                                        properties['addresses']  )
                            elif print_rr_type == 'SRVRecord':
                                if print_csv:
                                    printStr = srv_csv2xml % ( configuration, view, zone, Name_sameASzone_str, 
                                        update_flag, ttl, properties['priority'], properties['weight'], 
                                            properties['port'], properties['linkedRecordName'] )
                                else:
                                    printStr = ( "%s, %s, %s, Record Type:%s Name:%s port:%s priority:%s" 
                                                  " weight:%s linkedRecordName:%s" ) % ( configuration,
                                                   view, zone, 'SRV', Name_sameASzone_str,
                                                   properties['port'], properties['priority'], properties['weight'], 
                                                   properties['linkedRecordName'] )

                            elif print_rr_type == 'A':
                                if print_csv:
                                    printStr = a_csv2xml % (configuration, view, zone, Name_sameASzone_str, 
                                        update_flag, ttl, properties['rdata'] )
                                else:
                                    printStr = "%s, %s, %s, Record Type:%s Name:%s Rdata:%s" % ( configuration,
                                        view, zone, properties['type'], Name_sameASzone_str, 
                                        properties['rdata']  )
                                
                            elif print_rr_type == 'AAAA':
                                if print_csv:
                                    printStr = aaaa_csv2xml % (configuration, view, zone, Name_sameASzone_str, 
                                        update_flag, ttl, properties['rdata'] )
                                else:
                                    printStr = "%s, %s, %s, Record Type:%s Name:%s Rdata:%s" % ( configuration,
                                        view, zone, 'AAAA', Name_sameASzone_str, 
                                        properties['rdata']  )
                                
                            elif print_rr_type == 'AliasRecord':
                                if print_csv:
                                    printStr = cname_csv2xml % ( configuration, view, zone, Name_sameASzone_str,  
                                        update_flag, ttl, properties['linkedRecordName']  )
                                else:                                
                                    printStr = "%s, %s, %s, Record Type:%s Name:%s LinkedRecordName:%s" % (configuration, 
                                        view, zone, 'CNAME', Name_sameASzone_str, properties['linkedRecordName']  )
                                        
                            elif print_rr_type == 'MXRecord':
                                if print_csv:
                                    printStr = mx_csv2xml % ( configuration, view, zone, Name_sameASzone_str,  
                                        update_flag, ttl, properties['linkedRecordName']  )
                                else:
                                    printStr = "%s, %s, %s, Record Type:%s Name:%s LinkedRecordName:%s" % (configuration,
                                        view, zone, 'MX', Name_sameASzone_str, properties['linkedRecordName']  )
                                                           
                            elif print_rr_type == 'TXTRecord':
                                if print_csv:
                                    printStr = txt_csv2xml % ( configuration, view, zone, Name_sameASzone_str,  
                                        update_flag, ttl, properties['txt']  )
                                else:
                                    printStr = "%s, %s, %s, Record Type:%s Name:%s TXT:%s" % (configuration,
                                        view, zone, 'TXT', Name_sameASzone_str, properties['txt']   )
                                
                            elif print_rr_type == 'HINFORecord':
                                if print_csv:
                                    printStr = hinfo_csv2xml % ( configuration, view, zone, Name_sameASzone_str, 
                                        update_flag, ttl, properties['os'], properties['cpu'] )
                                else:
                                    printStr = "%s, %s, %s, Record Type:%s Name:%s os:%s cpu:%s" % ( configuration, 
                                        view, zone, 'HINFO', Name_sameASzone_str, properties['os'], 
                                        properties['cpu'])
                            
                            else: #of if print_rr_type = 'ns':
                                Name_sameASzone_str = 'Unknown_Type'
                                if print_csv:
                                    printStr = cname_csv2xml % ( configuration, view, zone, Name_sameASzone_str,  
                                        update_flag,ttl,''  )
                                else:
                                    printStr = "%s, %s, %s, Record Type:%s Name:%s Rdata:%s" % (
                                        configuration, view, zone, properties['type'], Name_sameASzone_str, 
                                        properties['rdata']  )
                                    
                            #endof if print_rr_type = 'ns':


                            # ------------------------------------------------
                            # print to console or print to file 
                            # ------------------------------------------------
                            if print_go:
                                if print_it:
                                    print( printStr )
                                    
                                if f_out:   # write to file
                                    try:
                                        f_out.write( printStr + '\n' )
                                    except IOError:
                                        print ("Error: Open file %s error" % output_file)
                                        if f_out:
                                            f_out.close()
                                        return(1)
                                print_count = print_count + 1
                            #end of if print_go:
                            rr_count = rr_count + 1
                            
                        #endof for item in rtn:
                    #endof if dump_all:
                #endof if zone:
            #endof if view:
        #endof if configuration:
        return (print_count)
        
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        # print_log.go(log_error, logMsg + passed_args)
        #print(log_error, logMsg + passed_args)
        print(log_error, logMsg )
        if f_out:
            f_out.close()
        return (1)

# ---------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------
if __name__ == '__main__':
    dump_rr() 
    
    
