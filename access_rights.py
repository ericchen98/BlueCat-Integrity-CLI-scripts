#!/usr/bin/python3
# coding:utf-8
#
# Copyright 2021 BlueCat Networks. This software is released under an
# OSI-approved license, the Python Software License 2.0. This license is
# incorporated by reference. The license grants you certain rights.
# https://opensource.org/licenses/Python-2.0
#
# Bluecat only provides this Script for reference as a Proof of Concept
#
# program name: a-delete.py
# by: Eric Chen (hchen@bluecatnetworks.com)
# python ver: python 3
# BAM ver: 26.1
# 
# v5.7-2023-828 fixed log does not show in cli.py issue 
# v5.6-20221226 change log dir to "./"
# v5.5-20220221 update BAM.bam_logout(bam) before all return()
# v5.4 20220217 add IPv6 support
# v5.3 20211206 update help
# v5.2 update
# v5.1 20210921 (use BAM.py v20210918-1735)
# v5.0 20210915-1500
# v3.1 2020/5/26 read config file from dir: /opt/bluecat/cli
# v3.0 2020-0511 (Eric modify) - check access-rights-2020-0511-ok-with-print.py
#   1) add log
#   2) add -u user, -g  (re-write program)
# v2.0 update help for -b and -N
#
# The program has several switches and parameters.
#   -q -- runs quietly
#   -n -- makes no changes (dry run)
#   -d -- debug (print REST calls)
#   -o      print the list of overrides
#
#   -a right  add new access right (HIDE VIEW ADD CHANGE FULL)
#   -r        remvoe any access right
#   -c configuration
#   -b IP4Block (CIDR notation)
#   -N IP4Network (CIDR notation)
#   -v view
#   -z zone
#   -u user
#   -g usergroup
#
#   [ overrides ... ] -- a list of overrides to set. (Note:not support in new version)
# 
# You can also use a wildcard with the username, so if the usernames are
# structured, like staff_bill, staff_joe, you can say staff_* for the username
# and it will DTRT. Remember to use -u for users.
# 
# You can also make use of user groups. If bill and joe are in the staff group,
# you might want to give them permissions not individually, but through the staff
# group. Wildcards also apply there, too, so that if you have LDAP-created
# groups, you don't go crazy typing out huge long group names.


""" 
access-rights -a VIEW -c config1 -u user1 (add/update user1 VIEW ACL on config1)
access-rights -a FULL -c config1 -v view1 -u user1 (add/update user1 FULL ACL on view1 uner config1)
access-rights -a FULL -c config1 -v view1 -z test.corp -u user1 (add/update user1 FULL on test.corp under config1/view1)
access-rights -a FULL -c config1 -v view1 -z test.corp -g userGroup1 (add/update userGroup1 FULL on test.corp under config1/view1)

# remove ACL (-a should not be used with -r)
access-rights -r -c config1 -v view1 -z test.corp -u user1 (remove user1  ACL from zone test.corp under config1/view1)

# add/remove access right from IP block (--b4 or --n6)
access-rights -a FULL -c config1 --b4 10.0.0.0/8 -u user1 (add/update user1 with FULL ACL on IP4Block 10.0.0.0/8)
access-rights -r -c config1 --b4 10.0.0.0/8 -u user1 (remove user1 ACL from IP Block 10.0.0.0/8)
access-rights -a FULL -c config1 --b6 2001:db8::/64 -u user1 (add/update user1 with FULL on IP6Block 2001:db8::648)

# add/remove access right from IP Network (--n4 or --n6)
access-rights -a FULL -c config1 --n4 10.1.1.0/24 -u user1 (add user1 FULL ACL to IP4network 10.1.1.0/24)
access-rights -r -c config1 --n4 10.1.1.0/24 -u user1      (remove user1 ACL from IP4network 10.1.1.0/24)
access-rights -a FULL -c config1 --n6 2001:db8::/64 -u user1 (add user1 FULL ACL to IP6network 10.1.1.0/24)

-a ACL  add/update new access right (HIDE VIEW ADD CHANGE FULL)
-r remvoe any access right
-c configuration
-v view
-z zone
--b4 IP4Block (CIDR notation)
--n4 IP4Network (CIDR notation)
--b6 IP6Block (CIDR notation)
--n6 IP6Network (CIDR notation)
-u user
-g usergroup
"""

import getopt
import sys
import json
import fnmatch
import os

import BAM

# ---------------------------------------------------------------------
# New module to replace BAM
# ---------------------------------------------------------------------
# suppress InsecureRequestWarning for zeep when set "websession.verify = False"
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------
# global var
# ---------------------------------------------------------------------

version = "5.7"

# to disable exception trackback information (if not set, urllib3 excpetion will be printed to screen)
#sys.tracebacklimit = 0

log_info = 0
log_error = 1

# ---------------------------------------------------------------------
# set_access_right()
# ---------------------------------------------------------------------
def set_access_right(print_log, bam, entityname, groupname, access, entityid=None, groupid=None, overenable=False ):
    
    if entityid is None:
        try:
            tag = bam.getEntityByName(0, entityname, "Configuration")
        except:
            logMsg = str(e)
            print_log.go(log_error, logMsg)
            return (1) 
        if  tag['id'] == 0:
            logMsg = "The Tag Group '%s' does not exist." % entityname
            print_log.go(log_error, logMsg)
            return (1) 
        else:
            entityid = tag['id']

    if groupid is None:
        group = bam.getEntityByName(0, groupname, "UserGroup")
        
        if group['id'] == 0:
            logMsg = "The User Group '%s' does not exist." % groupname
            print_log.go(log_error, logMsg)
            return (1)
        else:
            groupid = group['id']

        
    # groupid could be "user id" or "group id"
    for ar in bam.getAllAccessRightsForUser(groupid):
    
        if ar['entityId'] != entityid: continue

        # here: ar['entityId'] == entityid -> this entity is the one we want to assign
        
        try:
            gar = bam.getAccessRight(ar['entityId'], ar['userId'])
        except ValueError as e:
            logMsg = "Failure: %s fail to get AccessRight" % str(e)
            print_log.go(log_error, logMsg)
            BAM.bam_logout(bam)
            return (1)

        arv = ar['value']
        if arv != gar['value']:
            print ("*** access rights inherited")

        overrides = ar['overrides']
        if overrides is None: overrides = '|'
        if type(overenable) == type([]):
            overrides = "|".join(overenable)

        if access and arv == access and not overenable:
            #if noisy: print groupname,"already has",arv,"over",entityname

            logMsg = "Failure: %s already has ACL %s on %s " % (groupname, arv, entityname)
            print_log.go(log_error, logMsg)
            return (1)

        elif access:
            #if noisy: 
            #    print groupname,no+"getting",arv,"over",entityname
            
            try:
                rtn = bam.updateAccessRight(entityid, groupid, access, overrides, ar['properties'])
                logMsg =  "Success: Updated %s access right %s to %s" % ( groupname, access, entityname)
                print_log.go(log_info, logMsg)
            except ValueError as e:
                logMsg = "Failure: %s fail to get record" % str(e)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
            
        elif access is None:
            try:
                bam.deleteAccessRight(entityid, groupid)
            except ValueError as e:
                logMsg = "Failure: %s fail to delete record" % str(e)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
            
            logMsg =  "Success: deleted %s Access right %s from %s" % ( groupname,  arv, entityname)
            print_log.go(log_info, logMsg)
            
        else:
            # if noisy: print groupname,"has",arv,"on",entityname
            pass
            
        if overenable is not False:
            #if noisy: 
            #    print groupname,"and",entityname,"have",overrides.replace("|", " ")
            pass
                
        break
        
    else:   # else (of for): the following codes will be run only when for loop run completed and not be "break"
        
        overrides = "|"
        
        if type(overenable) == type([]):
            overrides = "|".join(overenable)
            
        if access:
            bam.addAccessRight(entityid, groupid, access, overrides, "|")
            
            #if noisy: 
                # adding access right FULL over test.corp to user1
                #print no+"adding access right",access,"over",entityname,"to",groupname

            logMsg =  "Success: Added %s Access right %s to %s" % ( groupname, access, entityname )
            print_log.go(log_info, logMsg)
        
            
        elif access is None:
            #if noisy: 
                # user1 has no access right over test.corp to remove
                # print groupname,"has no access right over",entityname,"to remove"
            
            logMsg = "Failure: %s has no Access right on %s to remvoe" % (groupname, entityname)
            print_log.go(log_error, logMsg)

        else:
            #if noisy: 
                # print "no existing access right over",entityname,"to",groupname
                
            logMsg = "Failure: %s has no Access right on %s" % (groupname, entityname)
            print_log.go(log_error, logMsg)
        
# ---------------------------------------------------------------------
# main function
# ---------------------------------------------------------------------
def access_rights(*args):

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
    log_prog_type_index = prog_type_delete

    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    # default = 3 sec. If change any  other number, it will overwrite 
    #       REST requests timeout value
    req_timeout = 5

    # read max obj count in API
    max_obj_count = "1000"

    # ---------------------------------------------------------------------
    # local var setup
    # ---------------------------------------------------------------------
    logMsg = ''
    logMsg2 = ''        # for query script to build multiple result
    cmdLine = ''
    input_cmd = ''
    input_cmd_log = ''
   
    # log_info_error = 0(info), 1(error). This is used tl call bam.print_log()
    log_info = 0
    log_error = 1

    api=''
    apiPw=''
    apiPw_decode = ''
    https=False

    configuration = None
    view = None
    zone = None
    rrName = None
    rdata = None
    matchclient = None
    user = None
    debug = False
    show_version = False
    
    access = ""

    userName = None
    groupUserName = None
    overenable = False

    groupname = None

    ip4BlockName = None
    ip4NetworkName = None
    
    ip6BlockName = None
    ip6NetworkName = None
    
    entitytype = None
    entityname = None

    confid = 0
    viewid = 0
    zoneid = 0

    sameAsZone = None
    record_changed = False

    # just give it add for set up
    new_log_prog_type_index = prog_type_add 

    # ------------------------------------------ for debug
    debug = False           # -d of getopt() 
    debug_input = None      # input (type str) of getopt()
    debug_user = False
    debug_api  = False
    debug_bam  = False

    # ------ set up program home dir for Win & Linux ------
    workingDir = ''
    if os.name == 'nt':
        #  same dir in Windows
        workingDir = "./"
        logPath = "./"
        logFileName = "cli"
    else:
        # Linux platform
        workingDir = "./"
        logPath = "./"
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
        print_log.go(log_error, logMsg)
        return (1)  
        
    # ---------------------------------------------------------
    # read from CLI
    # ---------------------------------------------------------
    input_args = list(args)   # args is the arguments passed by calling this function.
                              # use new var just because getopt() also use "args" as output
    try:
        if len(input_args)!=0:    #this is called by other python script
            opts, args = getopt.getopt(  input_args, "qdb:N:n:z:c:v:u:g:oa:rh", ["debug=","version"])
        else: # call this script from CLI. Parsing "sys.argv[1:]" ([1:] - not include script name)
            opts, args = getopt.getopt(sys.argv[1:], "qdb:N:n:z:c:v:u:g:oa:rh", ["b4=","n4=","b6=","n6=", "debug=","version"])
    except getopt.GetoptError as e:
        logMsg = str(e)
        print_log.go(log_error, logMsg)
        return (1) 

    for o,v in opts:
        if o == "-d": debug = True
        elif o == "--b4": 
            entitytype = "IP4Block"
            ip4BlockName = v
            if (ip4BlockName[0:1] == "-"):
                print ("-b parameter empty error")
                return (1)
                
        elif o == "--n4": 
            entitytype = "IP4Network"
            ip4NetworkName = v
            if (ip4NetworkName[0:1] == "-"):
                print ("-N parameter empty error")
                return (1)

        elif o == "--b6": 
            entitytype = "IP6Block"
            ip6BlockName = v
            if (ip6BlockName[0:1] == "-"):
                print ("-b parameter empty error")
                return (1)

        elif o == "--n6": 
            entitytype = "IP6Network"
            ip6NetworkName = v
            if (ip6NetworkName[0:1] == "-"):
                print ("-N parameter empty error")
                return (1)

        elif o == "-z": 
            entitytype = "Zone"
            zone = v
            if (zone[0:1] == "-"):
                print ("-z parameter empty error")
                return (1)
        
        elif o == "-c": 
            #entitytype = "Configuration"
            configuration = v
 
            if (configuration[0:1] == "-"):
                print ("-c parameter empty error")
                return (1)
 
            # entityname = v
        elif o == "-v": 
            view = v
            if (view[0:1] == "-"):
                print ("-v parameter empty error")
                return (1)

        elif o == "-u": 
            user = True
            userName = v

        elif o == "-g": 
            groupUserName = v
            
        elif o == "-o": overenable = True
        elif o == "-a":
        
            # use "add" in log
            new_log_prog_type_index = prog_type_add

            if not access=="":
                logMsg = "Failure: access rights have already been chosen"
                
                print_log.go(log_error, logMsg)
                return (1) 
            access = v
            
        elif o == "-r":
            #assert access=="", "access rights have already been chosen"
            
            # use "add" in log
            new_log_prog_type_index = prog_type_delete
            
            if not access=="":
                logMsg = "Failure: access rights have already been chosen"
                print_log.go(log_error, logMsg)
                return (1)
            access = None
            
        elif o == "-h":
            print (__doc__)
            return (0)
    
    if not opts:
        print (__doc__)
        return (0)
    
    if show_version == True:
        print("Version %s" % version)
        return(0)
    
    # chagne log "add"/"delete"/"view" type
    print_log.change_type(new_log_prog_type_index)

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

    #---------------------------------------------------------------------
    # check cofig
    #---------------------------------------------------------------------
    
    if (not configuration):
        logMsg = "Failure: -c config option is required"
        print_log.go(log_error, logMsg)
        return (1)
    else:
        entitytype = "Configuration"
        entityname =  configuration
    
        
    if (view or zone) and (ip4BlockName or ip4NetworkName):
        print ("too many argument  (-v or -z) cannot work with (-b or -N) ")
        return (1) 

    if view or zone:
        if view:
            # config is checked before
            entitytype = "View"
            entityname =  view
        if zone:
            # config is checked before
            if not view:
                print ("Error: view is required")
                return (1)
            else:
                entitytype = "Zone"
                entityname =  zone
    else: # of if view and zone:
        if ip4BlockName and ip4NetworkName:
            print ("Error: Can only use either --b4 or --n4")
            return (1) 
        if ip6BlockName and ip6NetworkName:
            print ("Error: Can only use either --b6 or --n6")
            return (1) 
            
        if ip4BlockName:
            # config is checked before
            entitytype = "IP4Block"
            entityname =  ip4BlockName
        if ip4NetworkName:
            # config is checked before
            entitytype = "IP4Network"
            entityname =  ip4NetworkName
            
        if ip6BlockName:
            # config is checked before
            entitytype = "IP6Block"
            entityname =  ip6BlockName
        if ip6NetworkName:
            # config is checked before
            entitytype = "IP6Network"
            entityname =  ip6NetworkName
            
            
            
    if access is not None:
        access = access.upper()
        #if access: assert access in "HIDE VIEW ADD CHANGE FULL".split()
        
        # print "HIDE VIEW ADD CHANGE FULL".split()
        # ['HIDE', 'VIEW', 'ADD', 'CHANGE', 'FULL']
        
        if not access == None:
            if not access in "HIDE VIEW ADD CHANGE FULL".split():
                logMsg = "Failure: parameter error. Access right needs to any of [HIDE VIEW ADD CHANGE FULL]"
                print_log.go(log_error, logMsg)
                return (1)         
    
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
    target_ent_id = 0
    
    try:
        if configuration:
            config_ent = bam.getEntityByName("0", configuration, "Configuration")
            confid = config_ent['id']
            if confid == 0:
                logMsg = "Failure: Failed to get configuration: %s" % (configuration)
                print_log.go(log_error, logMsg)
                return (1)
            else:
                target_ent_id = confid
        #----------------------------------------------------------
        if view:
            view_ent = bam.getEntityByName(confid, view, "View")
            viewid = view_ent['id']
            if viewid == 0:
                logMsg = "Failure: Failed to get view: %s" % (view)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
            else:    
                target_ent_id = confid
        
        '''
        if entitytype in [ "TagGroup", "Configuration" ]:
        elif entitytype == "View":
        elif entitytype == "Zone":
        elif entitytype == "IP4Block" or entitytype == "IP4Network":
        else:
            logMsg = "Failure: No match for the entitytype %s and entityname %s" % (entitytype, entityname)
        '''
        
        # note-20210914: TagGroup is not used in this program
        if entitytype in [ "TagGroup", "Configuration" ]:
            
            try:
                entity = bam.getEntityByName( 0, entityname , entitytype )
                target_ent_id =  entity['id']
            except ValueError as e:
                logMsg = "Failure: "+str(e) + "Error while getting " + entityname
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)

            #read config twice??? this block can be deleted
            #print(target_ent_id)

        #----------------------------------------------------------
        elif entitytype == "View":
            try:
                entity = bam.getEntityByName(confid, view, "View")
                target_ent_id = entity['id']
            
            except ValueError as e:
                logMsg = "Failure: "+str(e) + "Error while getting " + entityname
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
        #----------------------------------------------------------    
        elif entitytype == "Zone":
        
            try:
                entity = bam.find_zone(viewid, entityname)
                zoneid = entity['id']
            except ValueError as e:
                logMsg = "Failure: "+str(e) + "Error while getting " + entityname
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
                
            if zoneid == 0:
                logMsg = "Failure:Failed to get zone: %s" % (zone)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return(1)
            else:
                target_ent_id =  zoneid
        #----------------------------------------------------------
        
        # org before add ipv6 
        #elif entitytype == "IP4Block" or entitytype == "IP4Network":
        
        elif entitytype == "IP4Block" or entitytype == "IP4Network" or entitytype == "IP6Block" or entitytype == "IP6Network":
            
            entities = list( bam.searchAllByObjectTypes(entityname, entitytype) )
            
            # print(entities)
            
            '''
            note: entities = list(bam.searchAllByObjectTypes()) will return all entities under all configuration. 
                  need to filter out untarget config.
                Example of search restult list:
                    config1     -> 10.0.0.0/8 (id 10094) <--- the block we want to set access right
                    config-demo -> 10.0.0.0/8 (id 10077) <--- this is not our target
            '''
            
            # scan all items (ent) in entities. If its id == configid, then put into entities_rtn
            # result: entities_rtn will be all items that "parent's config id == confid"
            entities_rtn = filter( lambda ent: bam.getConfiguration(ent['id']) == confid, entities )
            
            # note: if we run "print( list(entities_rtn) )" for debug, the next list(entities_rtn) will be empty!!

            # convert filter obj to list (by test, it is required for py3)
            entities = list(entities_rtn)

            #assert len(entities) >= 1, "The %s '%s' does not exist." % (entitytype, entityname)            
            if not (len(entities) >= 1):
                logMsg = "Failure: The %s %s does not exist" % ( entitytype, entityname)
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
            
            # assert len(entities) == 1, "somehow you got more than one block or network: %s" % str(entities)
            if not (len(entities) == 1):
                logMsg = "Failure: somehow you got more than one block or network: %s" % ( str(entities) )
                print_log.go(log_error, logMsg)
                BAM.bam_logout(bam)
                return (1)
            
            entity = entities[0]
            target_ent_id = entity['id']

        #----------------------------------------------------------
        else:
            logMsg = "Failure: No match for the entitytype %s and entityname %s" % (entitytype, entityname)
            print_log.go(log_error, logMsg)
            BAM.bam_logout(bam)
            return (1)
            
        # endof if entitytype in [ "TagGroup", "Configuration" ]:

            
        #assert entity['id'], "The %s '%s' does not exist." % (entitytype, entityname)

        entityid = target_ent_id
        if entityid == 0:
            logMsg = "The %s '%s' does not exist." % (entitytype, entityname)
            print_log.go(log_error, logMsg)
            BAM.bam_logout(bam)
            return (1)
        
        people = "UserGroup"
        if user:
            people = "User"
            
        if args:
            overenable = args
        
        FoundUser = False
        
        for usergroup in bam.getAllEntities(0, people):
            ugname = usergroup['name']
            
            # add by Eric because we use -u and -g now
            if userName:
                groupname = userName
            else:
                groupname = groupUserName

            if groupname == None:     # added by Eric. Found if groupname == None will cause fnmatch.fnmatch() error
                groupname = ''

            if fnmatch.fnmatch(ugname, groupname):
                FoundUser = True    # added by Eric. To print error message
                
                #print('---------------------------------------------------------------')
                #print(entityname, ugname, access, entityid, usergroup['id'], overenable)
                #print('---------------------------------------------------------------')

                set_access_right( print_log, bam, entityname, ugname, access, entityid, 
                    groupid = usergroup['id'], overenable=overenable) 


        if not FoundUser:
            logMsg = "Failure: cannot find user or userGroup: %s" % groupname
            print_log.go(log_error, logMsg)
            # exit is not require here (this is end of prog)
            # return (1) 


    except ValueError as e:     # except fosr any api error
        logMsg = "%s" % ( str(e) )
        print_log.go(log_error, logMsg)
        BAM.bam_logout(bam) 
        exit(1)


# ---------------------------------------------------------------------
# start
# ---------------------------------------------------------------------
if __name__ == '__main__':
    access_rights()
