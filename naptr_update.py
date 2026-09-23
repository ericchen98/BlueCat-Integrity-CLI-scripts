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
#
# ----------------------------- INPORTANT NOTE --------------------------
# when running this script under bash, -e & --ne need to be quoted: e.g. -e '!^.*$!sip:user@sip.rfc1035.com!'
# because !^ will be translated to input command. The -e will become "naptr-update.py.*$!sip:user@sip.rfc1035.com!"
# it will cause BAM deploy failur (regex error)
#
# when running this script under cli.sh, -e & --ne must not be quoted!!
# -----------------------------------------------------------------------
#
# v5.7-20230828 fixed log does not show in cli.py issue 
# v5.6-20221220
#       1) modified: logPath = "./"
#       2) add flag convertRR=True to convert RR Name and rdata to "lower case".
# v5.5-20220415 per request, check input field: order & preference range in 0~65535 
# v5.4-20220402 modify var setup:  neworder = "0" and  newpreference = "0" to meet the original POC cmd
# v5.3-20220221 update BAM.bam_logout(bam) before all return()
# v5.2-2021-1202
# v5.1-20210921 (use BAM.py v20210918-1735)
# v5.0 20210915-1500
# v3.0.2 2021/8/1 use new BAM that work with 9.3 & REST
#       - modify to work with python 3
#       - use bam.find_zone()
#       - use print_log class in BAM.py
#       - use pw in BAM
#       - use bam.update() to update record (don't need delete() then add() anymore)
#         note: after patch is applied, api support updating naptr with empty regex. 
#

'''
naptr-update -c config1 -v view1 -z test.corp -r naptr1 -g S -o 100 -p 10 -e !^.*$!sip:user@sip.rfc1035.com! -t test1.MNC001.MCC700.gprs. -s x-3gpp-pgw:x-gp:x-gn --ng 9 --no 999 --np 9 --ne !^.*$!sip:user@sip.rfc1035.com.999! --nt test1.MNC001.MCC999.gprs.new.999 --ns x-3gpp-pgw:x-gp:x-gn.new.999

    -c config name -v view name -z zone name -r record name
    -g flags          --ng new_flags
    -o order          --no new_order
    -p preference     --np new_preference
    -e regexp         --ne new_regexp
    -t replacement    --nt new_replacement    
    -s service        --ns new_service
    -k same as zome record (when -k is used, -r is ignored)
'''

import getopt
import sys
import json
import os

import BAM

# ---------------------------------------------------------------------
# New module to replace BAM (zeep, SOAP)
# ---------------------------------------------------------------------
# suppress InsecureRequestWarning for zeep when set "websession.verify = False"
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------

version = "5.7"

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
def naptr_update(*args):    

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
    log_prog_type_index = prog_type_update

    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    # default = 3 sec. If change any  other number, it will overwrite 
    #       REST requests timeout value
    req_timeout = 5

    # read max obj count in API
    max_obj_count = "1000"

    # ---------------------------------------------------------------------
    # local var 
    # ---------------------------------------------------------------------

    logMsg = ''
    logMsg2 = ''        # for query script to build multiple result
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''

    api = ''
    apiPw = ''
    apiPw_decode = ''
    https = False
    
    configuration = None
    view = None
    zone = None
    rrName = None
    rdata = None
    show_version = False

    confid = 0
    viewid = 0
    zoneid = 0

    
    order = ""
    preference = ""
    service = ""
    regexp = ""
    replacement = ""
    flags = ""
    
    neworder = "0"
    newpreference = "0"
    newservice = ""
    newregexp = ""
    newreplacement = ""
    newflags = ""
    
    sameAsZone = None
    searchrrName = None
    absolutename = None
    add_absolutename = None
    
    
    error_Logged = False    # True when bam.update exception is called
    record_changed = False

    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    debug_user = False
    debug_api  = False
    debug_bam  = False

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
        
    #-------------------------------------------------------------------
    # load config by BAM.load_config()  return json format "config"
    #-------------------------------------------------------------------
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
        print_log.go(log_error, logMsg)
        return(1)  

    # ---------------------------------------------------------
    # read from CLI
    # ---------------------------------------------------------
    input_args = list(args)   # args is the arguments passed by calling this function.
    try:
        # this is to prepare if this script is called by other python script.
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(  input_args, "dc:v:z:r:g:o:p:e:t:s:kh",["ng=","no=","np=","ne=","nt=","ns=","debug=","version"] )            
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "dc:v:z:r:g:o:p:e:t:s:kh",["ng=","no=","np=","ne=","nt=","ns=","debug=","version"] )
    except getopt.GetoptError as e: 
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return(1) 

    for o,v in opts:
        if o == "-d": debug = True
        elif o == "-c": configuration = v
        elif o == "-v": view = v
        elif o == "-z": zone = v
        elif o == "-r": rrName = v
        elif o == "-g": flags = v
        elif o == "-o": order = v
        elif o == "-p": preference = v
        elif o == "-e": regexp = v
        elif o == "-t": replacement = v
        elif o == "-s": service = v  
        elif o == "--ng": newflags = v  
        elif o == "--no": neworder = v
        elif o == "--ne": newregexp = v
        elif o == "--np": newpreference = v
        elif o == "--nt": newreplacement = v
        elif o == "--ns": newservice = v
        elif o == "-k": sameAsZone = True
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
        debug_user = True           # enabled by -d
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


    if debug_api:
        print ("--------------[debug: input parameter] ---------------")
        print(opts)
        print("")

    # ---------------------------------------------------------
    # test cli required parameters 
    # ---------------------------------------------------------
    if (not configuration) or (configuration[0:1] == "-"):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg)
        return(1)

    if (not view) or (view[0:1] == "-"):
        logMsg = "Failure: -v view option is required"
        print_log.go(log_error, logMsg)
        return(1)

    if (not zone) or (zone[0:1] == "-"):
        logMsg = "Failure: -z zone option is required"
        print_log.go(log_error, logMsg)
        return(1)

    if not sameAsZone:  # -k is not set check rrName
        if (rrName == None) or (rrName[0:1] == "-"):
            logMsg = "Failure: -r rrName option is required"
            print_log.go(log_error, logMsg)
            return(1)

    if (neworder):
        try:
            if ( 0<= int(neworder) <= 65535 ):
                pass
            else:
                logMsg = "Failure: --no (New_order) input error valid value:[0-65535]"
                print_log.go(log_error, logMsg)
                return(1)
        except:
            logMsg = "Failure: -o (order) input error valid value:[0-65535]"
            print_log.go(log_error, logMsg)
            return(1)

    if (newpreference):
        try:
            if ( 0<= int(newpreference) <= 65535 ):
                pass
            else:
                logMsg = "Failure: --np (New_preference) input error valid value:[0-65535]" 
                print_log.go(log_error, logMsg)
                return(1)
        except:
            logMsg = "Failure: -p (preference) input error valid value:[0-65535]"
            print_log.go(log_error, logMsg)
            return(1)


    #----------------------------------------------------------
    # -xx and --xx ... is not checked. should we fource user enter all parameters?
    #
    #if (newflags == None) or (newflags[0:1] == "-"):  
    #    logMsg = "--ng newflags option is required"
    #    print_log.go(log_error, logMsg)
    #    return(1)

    if sameAsZone:
        sameAsZone_Message = " SAME AS ZONE "
    else:
        sameAsZone_Message = " "
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
        logMsg = bam.mask_id_pw( str(e) )   # mask username and pw in e when login fail
        print_log.go(log_error, logMsg)
        return(1)    
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
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)

            if view:
                view_ent = bam.getEntityByName(confid, view, "View")
                viewid = view_ent['id']
                if viewid == 0:
                    logMsg = "Failure: Failed to get view: %s" % (view)
                    print_log.go(log_error, logMsg)
                    BAM.bam_logout(bam)
                    return(1)

                if zone:
                    zone_ent = bam.find_zone(viewid, zone)
                    zoneid = zone_ent['id']
                    if zoneid == 0:
                        logMsg = "Failure: Failed to get zone: %s" % (zone)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)
                    # ------------------------------------------------ 
                    # End of read config/view/zone 
                    # ------------------------------------------------ 
                    
                    # ------------------------------------------------ 
                    # convert zone & rrName to lower cases to meet requirement
                    # ------------------------------------------------ 
                    if convertRR:
                        if not (zone == None):
                            zone = zone.lower()
                        if not (rrName == None):
                            rrName = rrName.lower()
                        if not (service == None):
                            service = service.lower()
                        if not (replacement == None):
                            replacement = replacement.lower()
                        if not (flags == None):
                            flags = flags.lower()
                        if not (newservice == None):
                            newservice = newservice.lower()
                        if not (newreplacement == None):
                            newreplacement = newreplacement.lower()
                        if not (newflags == None):
                            newflags = newflags.lower()

                    if sameAsZone:
                        absolutename = zone
                        rrName=""
                    else:
                        absolutename = rrName + "." + zone

                    try:
                        result_list = bam.getEntitiesByName(zoneid, rrName, "NAPTRRecord", 0, max_obj_count)
                    except ValueError as e:
                        logMsg = "Failure: %s fail to get record" % str(e)
                        print_log.go(log_error, logMsg)
                        BAM.bam_logout(bam)
                        return(1)

                    if len(result_list) == 0: # no entity found
                        logMsg = "Failure: No%srecord found!" % sameAsZone_Message
                        print_log.go(log_error, logMsg)
                    else: # found entity
                        for ent in result_list:
                            properties = bam.splitProp(ent)
                            
                            if debug:
                                print ('\n################ Entity read ################')
                                print ('object id = %s' % ent['id'])
                                #print (ent)
                                #print ('properties=')
                                #print (properties)
                                print ('--------------------------------------absoluteName(existing vs input)')
                                print (properties['absoluteName'])
                                print (absolutename)
                                print ('--------------------------------------flags(existing vs input)')
                                print (properties['flags'])
                                print (flags)
                                print ('--------------------------------------order(existing vs input)')
                                print (properties['order'])
                                print (order)
                                print ('--------------------------------------preference(existing vs input)')
                                print (properties['preference'])
                                print (preference)
                                print ('--------------------------------------regexp(existing vs input)')
                                print (properties['regexp'])
                                print (regexp)
                                print ('--------------------------------------replacement(existing vs input)')
                                print (properties['replacement'])
                                print (replacement)
                                print ('--------------------------------------service(existing vs input)')
                                print (properties['service'])
                                print (service)
                                print ('----------------(end of record)----------------------\n')

                            if properties['absoluteName'] == absolutename and \
                               properties['flags'] == flags and \
                               properties['order'] == order and \
                               properties['preference'] == preference and \
                               properties['regexp'] == regexp and \
                               properties['replacement'] ==replacement and \
                               properties['service'] == service:
                            
                                # all fields match. process record
                            
                                # build this message
                                # (*) Record: a1.test.corp, IP: 1.1.1.2 -> is updating to IP: 2.1.1.2
                                
                                print ( "(*) Record: " + properties['absoluteName'] + ","  \
                                    + " type: " + "naptr" + "," \
                                    + " flags: " + properties['flags'] + "," \
                                    + " order: " + properties['order'] + "," \
                                    + " preference: " + properties['preference'] + "," \
                                    + " regexp: '" + properties['regexp'] + "'," \
                                    + " replacement: " + properties['replacement'] + "," \
                                    + " service: '" + properties['service'] + "' -> updating..." )
                                
                                # update all fields with new input
                                properties['flags'] = newflags
                                properties['order'] = neworder
                                properties['preference'] = newpreference
                                properties['regexp'] = newregexp
                                properties['replacement'] = newreplacement
                                properties['service'] = newservice
                                
                                ent['properties'] = bam.joinProp(properties)
                                
                                if debug:
                                    print ( '------ Ent to be used by bam.update(ent) -------')
                                    print (ent)
                                    # output
                                    # {'id': 171533, 'name': 'a1', 'type': 'GenericRecord', 
                                    #   'properties': 'absoluteName=a1.test.corp|type=A|rdata=1.1.1.21|'}
                                try:
                                    bam.update(ent)
                                    prnMsg = "Success: Update%srecord %s" % ( sameAsZone_Message, absolutename)
                                    print (prnMsg)
                                    record_changed = True
                                    
                                except ValueError as e:
                                    logMsg = "Failure: %s Failed to update%srecord: %s" % ( str(e), 
                                                                        sameAsZone_Message, absolutename)
                                    print_log.go(log_error, logMsg)
                                    record_changed = False
                                    error_Logged = True
                                    # cannot run return(1) as we want to pring the rest of records
                                                
                            else:  #of if properties['absoluteName'] == absolutename and..... (not match)
                                print ( "Record: " + properties['absoluteName'] + ","  \
                                    + " type: " + "naptr" + "," \
                                    + " flags: " + properties['flags'] + "," \
                                    + " order: " + properties['order'] + "," \
                                    + " preference: " + properties['preference'] + "," \
                                    + " regexp: '" + properties['regexp'] + "'," \
                                    + " replacement: " + properties['replacement'] + "," \
                                    + " service: '" + properties['service'] +"'" )
                                    
                            #endof if properties['absoluteName'] == absolutename and \
                        # endof for ent in result_list:
                        
                        # ----- print final success/Failure message ----------
                        if record_changed:
                            print ()
                            logMsg =  "Success: Update%srecord %s " % ( sameAsZone_Message, absolutename)
                            print_log.go(log_info, logMsg)
                            BAM.bam_logout(bam)
                            return(0)
                        else:
                            if not error_Logged:
                                print ()
                                # the log has been sent due to update exception. 
                                #     (To avoid sending duplicated log here)
                                logMsg = "Failure: failed to update%srecord %s" % ( sameAsZone_Message, 
                                                                            absolutename)
                                print_log.go(log_error, logMsg)
                                BAM.bam_logout(bam)
                                return(1)
                        #endof if record_changed:
                    #endof if len(result_list) == 0: # no entity found
                #endof if zone:
            #endof if view:
        #endof if configuration:
        BAM.bam_logout(bam)
        return(0)
        
    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        return(1)
# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    naptr_update()
                     
                    
                    
