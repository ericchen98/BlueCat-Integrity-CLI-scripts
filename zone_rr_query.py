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
# vt4 ignore case of record name. (convert it to upper case to compare)
#   todo: when write it to CSV, what case should the program write to?
#
# v5.1-20230828 fixed log does not show in cli.py issue 
# v5.0-20221220
#       1) modified: logPath = "./"
#       2) add flag convertRR=True to convert RR Name and rdata to "lower case".
# v4.0(t5)-20220221 update BAM.bam_logout(bam) before all return()
# v3.0 20211217 add -n that can filter record name
# v2.0 20211209
# v1.0 20211011 (use BAM.py v20211005-G)
# 
# supported record type:
#
# HostRecord HostRecord
# AliasRecord AliasRecord
# MXRecord MXRecord
# TXTRecord TXTRecord
# SRVRecord SRVRecord
# HINFORecord HINFORecord       : The Host Info or HINFO resource record contains optional text information about a host.
# NAPTRRecord NAPTRRecord
# GenericRecord GenericRecord

# return (0) if error and no record found
# else return number of found record

'''
zone-rr-query -c config1 -v view1 -z test.corp -a                      # print all RR
zone-rr-query -c config1 -v view1 -z test.corp -t naptr -n naptr1      # print naptr RR with name=naptr1
zone-rr-query -c config1 -v view1 -z test.corp -t naptr -r replace1    # print naptr RR with replacement=replace1

zone-rr-query -c config1 -v view1 -z test.corp -t ns                   # print all ns RR 
zone-rr-query -c config1 -v view1 -z test.corp -t ns -n ns1            # print all ns RR with name=ns1
zone-rr-query -c config1 -v view1 -z test.corp -t ns -r pc1.test.corp  # print all ns RR with rdata=pc1.test.corp

    -c config_name
    -v view_name
    -z zone_name
    -t rr_type      [host|cname|mx|txt|srv|naptr|generic|hinfo]
    -n record_name  (print only records' name matches record_name. Ignore case)
    -a              (dump all types of records, -t will be ignore)
    -r rdata        (for NAPTR and NS only. Query all records with same rdata. Ignore case)
    -p              (don't print output. used when this prog is called)
'''

# ------------- module from internet ---------

import getopt
import sys
import json
import os

# ------------- module by BlueCat ---------
import BAM

# ------------- module from internet ---------
import urllib3  # to suppress https cert worning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------
version = "5.1"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
sys.tracebacklimit = 0

#-------------------------------------------
# working & log path setup (Win & Linux)
#-------------------------------------------
win_workingDir = "./"
win_logPath = "./"
win_logFileName = "cli"
Linux_workingDir =  "./"
Linux_logPath =  "./"
Linux_logFileName = "cli"

#-------------------------------------------
# convertRR = False | False //whether to convert RR to lower cases when add/delete/query
#   A record: convert RR_Name
#-------------------------------------------
convertRR = False

# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------

# def dump_rr(zone_id, rr_type):

def zone_rr_query(*args):   
    
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
    req_timeout = 5

    # read max obj count in API
    max_obj_count = "10000"

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
    
    generic_subtype = ''
    

    show_version = False
    
    print_it = True
    dump_all = False
    query_name = ''
    
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
        workingDir = win_workingDir
        logPath = win_logPath
        logFileName = win_logFileName
    else:
        # Linux platform
        workingDir = Linux_workingDir
        logPath = Linux_logPath
        logFileName = Linux_logFileName

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
            opts, args = getopt.getopt(  input_args, "dc:v:z:t:an:r:ph", ["debug=","version"])           
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:v:z:t:an:r:ph", ["debug=","version"])
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
        
        elif o == "--version": show_version = True
        elif o == "--debug": debug_input = v  
        elif o == "-p": print_it = False
        elif o == "-h":
            print (__doc__)
            return(0)

    if not opts:
        print (__doc__)
        return(0)

    if show_version == True:
        print("Version %s" % version)
        return(0)

    #print('================================')
    #print(input_args)
    #print (opts)
    #print('================================')

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

    if (not view) or (view[0:1] == "-"):
        logMsg = "Failure: -v view option is required" 
        print_log.go(log_error, logMsg + passed_args)
        return(0)

    if (not zone) or (zone[0:1] == "-"): 
        logMsg = "Failure: -z zone option is required" 
        print_log.go(log_error, logMsg + passed_args)
        return(0)


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
            logMsg = "Failure: rrtype %s error" % ( rrtype )               
            print_log.go(log_error, logMsg + passed_args)
            return(0)


    if convertRR:
        if not (zone == None):
            zone = zone.lower()
        if not (rdata == None):
            rdata = rdata.lower()
        if not (query_name == None):
            query_name = query_name.lower()

    # ----------------------------------------------------------------
    # login to BAM
    # ----------------------------------------------------------------
    if https:
        BAM_URL = "https://" + config['hostname'] + "/Services/REST/v1/"
    else:
        BAM_URL = "http://" + config['hostname'] + "/Services/REST/v1/"       
    try:                   
        bam=BAM.BAM( BAM_URL, req_timeout)       
        response = bam.login( api, apiPw_decode )   #response.ok is checked in bam.login()
    except Exception as e:  # except of login()
        logMsg = bam.mask_id_pw( str(e) )  # mask username and pw in e when login fail
        print_log.go(log_error, logMsg + passed_args)
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
                print_log.go(log_error, logMsg + passed_args)
                BAM.bam_logout(bam)
                return(0)

            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    print_log.go(log_error, logMsg + passed_args)
                    BAM.bam_logout(bam)
                    return(0)

                if zone:
                    zone_ent = bam.find_zone(viewid, zone)
                    zoneid = zone_ent['id']
                    if zoneid == 0:
                        logMsg = "Failure: Failed to get zone: %s" % (zone)  
                        print_log.go(log_error, logMsg + passed_args)
                        BAM.bam_logout(bam)
                        return(0)
                    # ------------------------------------------------ 
                    # End of read config/view/zone 
                    # ------------------------------------------------ 
                    
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
                                        
                                print_log.go(log_error, logMsg + passed_args)
                                BAM.bam_logout(bam) 
                                return (0)
                            
                            rr_count_item = 0
                            
                            for item in rtn:

                                if print_it: 
                                    if debug_api:   # print raw format
                                        print(item)
                                        
                                    else: #
                                        # --------------------------------------------------------------
                                        # print RR with different format (for different RR TYPE)
                                        #    properties['absoluteName']   (might not need)
                                        # --------------------------------------------------------------
                                           
                                        Name_sameASzone_str = ''
                                        if item['name'] == '':
                                            Name_sameASzone_str = '(Same as Zone)'
                                        else:
                                            Name_sameASzone_str = item['name'] 
                                        properties = bam.splitProp(item)
                                        
                                        if item['type'] == "HostRecord":
                                            printStr = " Record Type:%-7s PTR:%-5s Name:%s IP:%s" % ( 'Host', 
                                                properties['reverseRecord'], Name_sameASzone_str, properties['addresses']  )
                                            print(printStr)
                                            
                                        elif item['type'] == "AliasRecord":
                                            printStr = " Record Type:%-7s Name:%s inkedRecordName:%s" % ( 'CNAME', 
                                                Name_sameASzone_str, properties['linkedRecordName']  )
                                            print(printStr)
                                            
                                        elif item['type'] == "MXRecord":
                                            printStr = " Record Type:%-7s Name:%s inkedRecordName:%s" % ( 'MX', 
                                                Name_sameASzone_str, properties['linkedRecordName']  )
                                            print(printStr)
                                            
                                        elif item['type'] == "TXTRecord":
                                            printStr = " Record Type:%-7s Name:%s inkedRecordName:%s" % ( 'TXT', 
                                                Name_sameASzone_str, properties['txt']  )
                                            print(printStr)
                                            
                                        elif item['type'] == "SRVRecord":
                                            printStr = ( " Record Type:%-7s Name:%s port:%s priority:%s" 
                                                          " weight:%s linkedRecordName:%s" ) % ( 
                                                           'SRV', Name_sameASzone_str,
                                                           properties['port'], properties['priority'], properties['weight'], 
                                                           properties['linkedRecordName']   
                                                         )
                                            print(printStr)
                                            
                                            
                                        elif item['type'] == "HINFORecord":
                                            printStr = " Record Type:%-7s Name:%s os:%s cpu:%s" % ( 'HINFO', 
                                                Name_sameASzone_str, properties['os'], properties['cpu']  )
                                            print(printStr)
                                        elif item['type'] == "NAPTRRecord":
                                            printStr = ( " Record Type:%-7s Name:%s order:%s preference:%s" 
                                                          " service:%s regexp:%s replacement:%s flags:%s" ) % ( 
                                                           'NAPTR', 
                                                           Name_sameASzone_str,
                                                           properties['order'], 
                                                           properties['preference'], 
                                                           properties['service'], 
                                                           properties['regexp'],
                                                           properties['replacement'],
                                                           properties['flags'],
                                                         )
                                            print(printStr)
                                            
                                        elif item['type'] == "GenericRecord":

                                            
                                        
                                            printStr = " Record Type:%-7s sub-type:%-5s Name:%s Rdata:%s" % ( 'Generic', 
                                                properties['type'], Name_sameASzone_str, properties['rdata']  )
                                            print(printStr)
                                            
                                        else:
                                            # in case thre's RR type not handled previously
                                            print(item)
                                
                                rr_count_item = rr_count_item + 1
                            rr_count = rr_count + rr_count_item
                            
                                
                        # endof for rr_type_item in rr_type:
                        
                        if debug_api:
                            print( "total: %s" % rr_count)
                        
                        # the final value is rr_count
                        
                    #-------------------------------------------------------------
                    # not dump all
                    #-------------------------------------------------------------

                    else: #of if dump_all: # not dump all, only dump a type of record
                        try:
                            rtn = bam.getAllEntities( zoneid, target_rrtype)
                        except ValueError as e:
                            logMsg = "Failure: %s Failed to dump zone %s record" % ( str(e), zone)
                                    
                            print_log.go(log_error, logMsg + passed_args)
                            BAM.bam_logout(bam) 
                            return (0)
                        
                        rr_count = 0
                        print_count = 0
                        
                        for item in rtn:
                            if print_it: 
                                Name_sameASzone_str = ''
                                if item['name'] == '':
                                    Name_sameASzone_str = '(Same as Zone)'
                                else:
                                    Name_sameASzone_str = item['name'] 
                                properties = bam.splitProp(item)
                                
                                #----------------------------------------------------    
                                if item['type'] == "HostRecord":
                                    if query_name == '': # mean print all
                                        printStr = " Record Type:%-7s PTR:%-5s Name:%s IP:%s" % ( 'Host', 
                                            properties['reverseRecord'], Name_sameASzone_str, properties['addresses']  )
                                        print(printStr)
                                        print_count = print_count + 1
                                    else:
                                        if item['name'].lower() == query_name.lower():
                                            printStr = " Record Type:%-7s PTR:%-5s Name:%s IP:%s" % ( 'Host', 
                                                properties['reverseRecord'], Name_sameASzone_str, properties['addresses']  )
                                            print(printStr)
                                            print_count = print_count + 1
                                #----------------------------------------------------    
                                elif item['type'] == "AliasRecord":
                                    if query_name == '': # mean print all
                                        printStr = " Record Type:%-7s Name:%s inkedRecordName:%s" % ( 'CNAME', 
                                            Name_sameASzone_str, properties['linkedRecordName']  )
                                        print(printStr)
                                        print_count = print_count + 1
                                    else:
                                        if item['name'].lower() == query_name.lower():
                                            printStr = " Record Type:%-7s Name:%s inkedRecordName:%s" % ( 'CNAME', 
                                                Name_sameASzone_str, properties['linkedRecordName']  )
                                            print(printStr)
                                            print_count = print_count + 1
                                #----------------------------------------------------    
                                elif item['type'] == "MXRecord":
                                    if query_name == '': # mean print all
                                        printStr = " Record Type:%-7s Name:%s inkedRecordName:%s" % ( 'MX', 
                                            Name_sameASzone_str, properties['linkedRecordName']  )
                                        print(printStr)
                                        print_count = print_count + 1
                                    else:
                                        if item['name'].lower() == query_name.lower():                                
                                            printStr = " Record Type:%-7s Name:%s inkedRecordName:%s" % ( 'MX', 
                                                Name_sameASzone_str, properties['linkedRecordName']  )
                                            print(printStr)
                                            print_count = print_count + 1
                                #----------------------------------------------------    
                                elif item['type'] == "TXTRecord":
                                
                                    if query_name == '': # mean print all
                                        printStr = " Record Type:%-7s Name:%s inkedRecordName:%s" % ( 'TXT', 
                                            Name_sameASzone_str, properties['txt']  )
                                            
                                        print(printStr)
                                        print_count = print_count + 1

                                    else:
                                        if item['name'].lower() == query_name.lower():                                
                                
                                            printStr = " Record Type:%-7s Name:%s inkedRecordName:%s" % ( 'TXT', 
                                                Name_sameASzone_str, properties['txt']  )
                                                
                                            print(printStr)
                                            print_count = print_count + 1
                                #----------------------------------------------------    
                                elif item['type'] == "SRVRecord":
                                
                                    if query_name == '': # mean print all
                                        printStr = ( " Record Type:%-7s Name:%s port:%s priority:%s" 
                                                      " weight:%s linkedRecordName:%s" ) % ( 
                                                       'SRV', Name_sameASzone_str,
                                                       properties['port'], properties['priority'], properties['weight'], 
                                                       properties['linkedRecordName']   
                                                     )
                                        print(printStr)
                                        print_count = print_count + 1
                                    else:
                                        if item['name'].lower() == query_name.lower():
                                            printStr = ( " Record Type:%-7s Name:%s port:%s priority:%s" 
                                                          " weight:%s linkedRecordName:%s" ) % ( 
                                                           'SRV', Name_sameASzone_str,
                                                           properties['port'], properties['priority'], properties['weight'], 
                                                           properties['linkedRecordName']   
                                                         )
                                            print(printStr)
                                            print_count = print_count + 1

                                #----------------------------------------------------    
                                elif item['type'] == "HINFORecord":
                                    if query_name == '': # mean print all
                                        printStr = " Record Type:%-7s Name:%s os:%s cpu:%s" % ( 'HINFO', 
                                            Name_sameASzone_str, properties['os'], properties['cpu']  )
                                        print(printStr)
                                        print_count = print_count + 1

                                    else:
                                        if item['name'].lower() == query_name.lower():                                
                                            printStr = " Record Type:%-7s Name:%s os:%s cpu:%s" % ( 'HINFO', 
                                                Name_sameASzone_str, properties['os'], properties['cpu']  )
                                            print(printStr)
                                            print_count = print_count + 1
                                #----------------------------------------------------    
                                elif item['type'] == "NAPTRRecord":
                                
                                    if query_name == '': # mean print all
                                        if rdata == '':     # rdata is not provided. Means print all 
                                            printStr = ( "Record Type:%-7s Name:%s order:%s preference:%s" 
                                                          " service:%s regexp:%s replacement:%s flags:%s" ) % ( 
                                                           'NAPTR', 
                                                           Name_sameASzone_str,
                                                           properties['order'], 
                                                           properties['preference'], 
                                                           properties['service'], 
                                                           properties['regexp'],
                                                           properties['replacement'],
                                                           properties['flags'],
                                                         )
                                            print(printStr)
                                            print_count = print_count + 1
                                        else: # print only match rdata record
                                            if rdata.lower() == properties['replacement'].lower():
                                                printStr = ( "Record Type:%-7s Name:%s order:%s preference:%s" 
                                                              " service:%s regexp:%s replacement:%s flags:%s" ) % ( 
                                                               'NAPTR', 
                                                               Name_sameASzone_str,
                                                               properties['order'], 
                                                               properties['preference'], 
                                                               properties['service'], 
                                                               properties['regexp'],
                                                               properties['replacement'],
                                                               properties['flags'],
                                                             )
                                                print(printStr)
                                                print_count = print_count + 1
                                            #endof if rdata == properties['replacement']:
                                        #endof if rdata == '':     # rdata is not provided. Means print all 
                                    else: #of if query_name == '': # mean print all
                                    
                                        if item['name'].lower() == query_name.lower():
                                            printStr = ( "Record Type:%-7s Name:%s order:%s preference:%s" 
                                                          " service:%s regexp:%s replacement:%s flags:%s" ) % ( 
                                                           'NAPTR', 
                                                           Name_sameASzone_str,
                                                           properties['order'], 
                                                           properties['preference'], 
                                                           properties['service'], 
                                                           properties['regexp'],
                                                           properties['replacement'],
                                                           properties['flags'],
                                                         )
                                            print(printStr)
                                            print_count = print_count + 1
                                        #endof if item['name'] == query_name:
                                    #endof if query_name == '': # mean print all
                                #----------------------------------------------------    
                                elif item['type'] == "GenericRecord":
                                
                                    if generic_subtype == 'A':  # test ok
                                        if properties['type']=='A':
                                        
                                            if query_name == '': # mean print all
                                                printStr = " Record Type:%-7s sub-type:%-5s Name:%s Rdata:%s" % ( 'Generic', 
                                                    properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                print(printStr)
                                                print_count = print_count + 1
                                            else:
                                                if item['name'].lower() == query_name.lower():
                                                    #printStr = " Record Type:%-7s sub-type:%-5s Name:%s Rdata:%s" % ( 'Generic', 
                                                    #    properties['type'], Name_sameASzone_str, properties['rdata']  )

                                                    printStr = " Record Type:%-5s Name:%s Rdata:%s" % ( 
                                                        properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                    print(printStr)
                                                    print_count = print_count + 1
                                    elif generic_subtype == 'AAAA': # test OK
                                        if properties['type']=='AAAA':
                                            if query_name == '': # mean print all
                                                #printStr = " Record Type:%-7s sub-type:%-5s Name:%s Rdata:%s" % ( 'Generic', 
                                                #    properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                
                                                printStr = " Record Type:%-5s Name:%s Rdata:%s" % ( 
                                                    properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                    
                                                print(printStr)
                                                print_count = print_count + 1
                                            else:
                                                if item['name'].lower() == query_name.lower():
                                                    #printStr = " Record Type:%-7s sub-type:%-5s Name:%s Rdata:%s" % ( 'Generic', 
                                                    #    properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                    printStr = " Record Type:%-5s Name:%s Rdata:%s" % (  
                                                        properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                        
                                                    print(printStr)
                                                    print_count = print_count + 1
                                                    
                                    elif generic_subtype == 'NS': # test OK
                                        if properties['type']=='NS':
                                            
                                            if query_name == '':    # means print all
                                                if rdata == '':     # rdata is not provided. Means print all 
                                                    #printStr = " Record Type:%-7s sub-type:%-5s Name:%s Rdata:%s" % ( 'Generic', 
                                                    #    properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                    printStr = " Record Type:%-5s Name:%s Rdata:%s" % ( 
                                                        properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                        
                                                    print(printStr)
                                                    print_count = print_count + 1
                                                
                                                else: # print only match rdata record
                                                    if rdata.lower() == properties['rdata'].lower():
                                                        #printStr = " Record Type:%-7s sub-type:%-5s Name:%s Rdata:%s" % ( 'Generic', 
                                                        #    properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                        printStr = " Record Type:%-5s Name:%s Rdata:%s" % ( 
                                                            properties['type'], Name_sameASzone_str, properties['rdata']  )

                                                        print(printStr)
                                                        print_count = print_count + 1
                                                # endof if rdata == '':
                                            
                                            else: # of if query_name == '': # print only RR's name match -n query_name
                                                
                                                if item['name'].lower() == query_name.lower():
                                                    #printStr = " Record Type:%-7s sub-type:%-5s Name:%s Rdata:%s" % ( 'Generic', 
                                                    #    properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                    printStr = " Record Type:%-5s Name:%s Rdata:%s" % ( 
                                                        properties['type'], Name_sameASzone_str, properties['rdata']  )
                                                        
                                                        
                                                    print(printStr)
                                                    print_count = print_count + 1
                                                    
                                    else: # ofif generic_subtype == 'A':   # mean others

                                        #printStr = " Record Type:%-7s sub-type:%-5s Name:%s Rdata:%s" % ( 'Generic', 
                                        #    properties['type'], Name_sameASzone_str, properties['rdata']  )
                                        printStr = " Record Type:%-5s Name:%s Rdata:%s" % ( 
                                            properties['type'], Name_sameASzone_str, properties['rdata']  )
                                            
                                        print(printStr)
                                        print_count = print_count + 1
                                else: # of if item['type'] == "HostRecord":
                                    # in case thre's RR type not handled previously
                                    print(item)
                                    print_count = print_count + 1
                                    
                            rr_count = rr_count + 1
                        #endof for item in rtn:
                        
                        if print_count == 0 and print_it: # when print_it = False, don't print this error mesg
                            logMsg = "Failure: no record found"
                            print_log.go(log_error, logMsg + passed_args)
                            BAM.bam_logout(bam)
                            return(1) 
                    #endof if dump_all:

                    # Note: the rr_count might not be the total zone records because 
                    #       bam.getAllEntities( zoneid, target_rrtype) will only get part of the record. 
                    # cann't use following way to count total records
                    # ---- don't use ----
                    # logMsg = "Success: dump zone data. Total zone record = %s, print = %s" % (rr_count, print_count)
                    # if print_it: print_log.go(log_info, logMsg + passed_args)
                    
                #endof if zone:
            #endof if view:
        #endof if configuration:
        BAM.bam_logout(bam)
        return (rr_count)
        
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg + passed_args)
        BAM.bam_logout(bam) 
        return (0)
# ---------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------
if __name__ == '__main__':
    zone_rr_query() 
    
    
