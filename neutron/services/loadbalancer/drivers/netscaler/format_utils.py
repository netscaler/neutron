# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013 Citrix Systems, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Youcef Laribi, Citrix

import json

import re
from xml.dom import minidom, Node
from xml.parsers.expat import ExpatError
#from lxml import etree

from neutron.openstack.common import log as logging

LOG = logging.getLogger(__name__)

def remove_whitespace_from_xml(xmlstr):
    return re.sub(">\s+<", "><", xmlstr)

def fromxml(xmlstr, plurals): 

    """minidom doesn't like whitespaces in an xml string"""
    """ so we'll first remove them """
    """ XXX - Need to move to use etree instead of minidom to avoid parsing twice""" 
    xmlstr = remove_whitespace_from_xml(xmlstr)  

    obj_dict = {}

    try:
        document = minidom.parseString(xmlstr)
    except ExpatError as e:
        LOG.error(_("XML parsing error: " + str(e.lineno)))
        raise Exception("Invalid XML input")

    rootNode = document.documentElement



    obj_dict[str(rootNode.nodeName)] = xmltodict(rootNode, plurals)


    return obj_dict



def xmltodict(parent, plurals):   

    LOG.debug(_("Entering xmltodict"))

    noAttributes = True

    obj_dict = {}
               
    attrs = parent.attributes
    
    parentName = parent.nodeName


    if attrs.keys() != None and len(attrs.keys()) != 0:

        for attrName in attrs.keys():
            attrNode = attrs.get(attrName)
            attrValue = attrNode.nodeValue
            LOG.debug(_("  " + attrName + " : " + attrValue))

            if attrName != "xmlns" and not attrName.startswith("xmlns:"):  
                obj_dict[str(attrName)] = str(attrValue)
                LOG.debug(_("obj_dict[" + str(attrName) + "] = " + str(attrValue)))
                noAttributes = False
 
    for node in parent.childNodes:

        LOG.debug(_("processing child node: " + node.nodeName))
        LOG.debug(_("child node's parent: " + parent.nodeName))
        LOG.debug(_("child node's contents: " + repr(node)))
        LOG.debug(_("child node's type: " + str(node.nodeType)))


         
        if node.nodeType == Node.ELEMENT_NODE:
            LOG.debug(_(node.nodeName + " is an element node."))
            if node.nodeName in obj_dict.keys():   
                LOG.debug(_("We already saw " +  node.nodeName))

                if isinstance(obj_dict[node.nodeName], list):
                    LOG.debug(_(node.nodeName + " is found to be a list"))
                    obj_dict[str(node.nodeName)].append(xmltodict(node, plurals))
                else:
                    LOG.debug(_(node.nodeName + " is not a list"))
                    val = obj_dict[str(node.nodeName)]
                    obj_dict[str(node.nodeName)] = []
                    obj_dict[str(node.nodeName)].append(val)
                    obj_dict[str(node.nodeName)].append(xmltodict(node, plurals)) 
                    LOG.debug(_("obj_dict[" + str(node.nodeName) + "] = " + str(obj_dict[node.nodeName])))
            else:    
                val = xmltodict(node, plurals)
                obj_dict[str(node.nodeName)] = val
                LOG.debug(_("obj_dict[" + str(node.nodeName) + "] = " + str(val)))


                 
        elif node.nodeType == Node.TEXT_NODE:
            LOG.debug(_(node.nodeName + " is an text node."))

            " If we are the only child of the parent node, and the parent node hasn't got attributes"
            " then we return the value of this text node now"    
            if (attrs.keys() == None or len(attrs.keys()) == 0) and len(parent.childNodes) == 1:
                return node.nodeValue
            
            val = node.nodeValue.strip()
            if val:
                obj_dict[str(parent.nodeName) + "__data"] =  val
                LOG.debug(_("obj_dict[" + str(parent.nodeName) + "__data] = " + str(val)))
        else:
            LOG.debug(_("Node  " + node.nodeName + " is not an element. It has type " + node.nodeType))
         
    if noAttributes:
        """ We check if there is only one element in obj_dict and it is a list"""
        LOG.debug(_("Node  " + parentName + " has no attributes"))
        LOG.debug(_("node " + parentName + " has got the following dictionary %s" % repr(obj_dict)))
        
        if len(obj_dict) == 1: 
            keylist = obj_dict.keys() 
            keyname = keylist[0]
                   
            LOG.debug(_("child Node  " + keyname + " of parent node " + parentName))
            LOG.debug(_("plurals: %s" % repr(plurals)))
            if plurals != None and keyname in plurals.keys():
                if plurals[keyname] == parentName:
                    LOG.debug(_(keyname + " is a singular of " + parentName))

                    if isinstance(obj_dict[keyname], list): 
                        LOG.debug(_("obj_dict[" + str(keyname) + " is already a list "))
                        return obj_dict[keyname]
                    else:
                        obj_list = [obj_dict[keyname]] 
                        return obj_list
        elif len(obj_dict) == 0:
            return []
    else:
        LOG.debug(_("Node  " + parentName + " has got attributes: " + str(attrs.keys())))

    LOG.debug(_("Exiting xmltodict"))
   
    return obj_dict



""" 
A very delicate function. Please modify with care, and test all possible conditions.

This function converts a python object to XML equivalent string where format is somewhat configurable.
"""

def toxml(attrname, attrval, plurals, xmlnamespace=None, firstTime=False, xmlstyle_as_elements=False):

    output = ""

    if attrval == None:
        return output

    objtype = type(attrval).__name__

    if objtype == 'str' or objtype == 'int':
        output += "<" + attrname + ">" + str(attrval) + "</" + attrname + ">"
        return output   

    if objtype == 'bool':

        if attrval:
            output += "<" + attrname + ">" + "true" + "</" + attrname + ">"
        else:
            output += "<" + attrname + ">" + "false" + "</" + attrname + ">"

        return output   

    LOG.debug(_("objtype is: %s for attribute name %s" % (objtype, attrname)))

    if objtype == 'unicode':
        attrval.encode('ascii','ignore')
        output += "<" + attrname + ">" + attrval + "</" + attrname + ">"
        return output   

    name = None
    
    if objtype == 'list':

        list_element_included = False
        LOG.debug(_("plurals in list value(%s) %s " % (attrval, str(plurals))))
        
        if attrval:      
            if plurals != None:
                singulars = dict(zip(plurals.values(), plurals.keys()))
                if attrname in singulars.keys():
                    name = singulars[attrname]

            if not name:
                name = attrname[0:-1]
            
            if attrname.lower().strip() != name.lower().strip():
                output += "<" + attrname

                if firstTime and xmlnamespace:
                    output += " xmlns=\"" + xmlnamespace + "\""
 
                output += ">"     
                
                list_element_included = True  
        
            for item in attrval:
                output += toxml(name, item, plurals, xmlstyle_as_elements=xmlstyle_as_elements)
                
            if list_element_included:
                output += "</" + attrname + ">"

        else:            
            output += "<" + attrname

            if firstTime and xmlnamespace:
                output += " xmlns=\"" + xmlnamespace + "\""
 
            output += "/>"


        return output

        
    if objtype == 'dict' or isinstance(attrval, object):
        
        output += "<" + attrname

        if firstTime and xmlnamespace:
            output += " xmlns=\"" + xmlnamespace + "\""

            
        complex_properties = dict() 

        firstItem = True
        
        for k in attrval:

            v = attrval[k]

            valtype = type(v).__name__
            
            LOG.debug(_("valtype of key %s is %s" % (k, valtype)))

            if k.startswith("_") and k != "_xsi_type":
                continue
            
            if k == "_xsi_type":
                output += " xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" "
                output += " xsi:type=\"" + v + "\""  
            elif (valtype == 'str' or valtype == 'unicode') and len(v) <= 512:
                
                if xmlstyle_as_elements:
                    if firstItem:
                        output += ">"
                        firstItem = False
                        
                    output += "<" + k + ">"
                    output += v
                    output += "</" + k + ">"
                else:
                    output += " " + k + "=" + "\"" + v + "\""
                    
            elif valtype == 'int' or valtype == 'bool':

                if xmlstyle_as_elements:
                    if firstItem:
                        output += ">"
                        firstItem = False
                        
                    output += "<" + k + ">"
                    if valtype == 'bool':
                        if v:
                            output += "true"
                        else:
                            output += "false"
                    else:  
                        output += str(v)

                    output += "</" + k + ">"

                else:
                    output += " " + k + "=" + "\""
                    if valtype == 'bool':
                        if v:
                            output += "true"
                        else:
                            output += "false"
                    else:  
                        output += str(v)

                    output += "\""

            else:
                    
                complex_properties[k] = v  

        if complex_properties:
            if (not xmlstyle_as_elements) or firstItem:
                output += ">"

            for k in complex_properties:
                v = complex_properties[k]
                output += toxml(k, v, plurals, xmlstyle_as_elements=xmlstyle_as_elements)

            output += "</" + attrname + ">"
        else:
            if (not xmlstyle_as_elements) or firstItem:
                output += "/>"
            else:
                output += "</" + attrname + ">"

        return output

    return output
       

def fromjson(payload, plurals):
    LOG.debug(_("starting fromjson"))
 
    obj_dict = json.loads(payload)

    LOG.debug(_("dictionary from json payload: " + str(obj_dict)))

    LOG.debug(_("exiting fromjson"))

    return obj_dict


def tojson(attrname, attrval, plurals):

    output = ""

    if attrval == None:
        return output

    objtype = type(attrval).__name__

    LOG.debug(_("objtype is: %s for attribute name %s" % (objtype, attrname)))
 
    if objtype == 'str':
        if attrname:
            output += "\"" + attrname + "\":"
 
        output += "\"" + str(attrval) + "\","
        return output  

    if objtype == 'int':
        if attrname:
            output += "\"" + attrname + "\":"
 
        output += str(attrval) + ","
        return output  

    if objtype == 'bool':
        if attrname:
            output += "\"" + attrname + "\":"
 
        if attrval == True:
            output += "true,"
        else:
            output += "false,"
            
        return output  


    if objtype == 'unicode':
        attrval.encode('ascii','ignore')
        if attrname:
            output += "\"" + attrname + "\":"
 
        output += "\"" + attrval + "\","
        return output  


    if objtype == 'list':
        if attrname:
            output += "\"" + attrname + "\":" 

        output += "["
             
        first = True

        if attrval:
            for item in attrval:
                if not first:
                    output += ","
                else:
                    first = False

                output += tojson(None, item, plurals)

        output += "]"

        return output

    if objtype == 'dict' or isinstance(attrval, object):
        if attrname:
            output += "\"" + attrname + "\":" 

        output += "{" 
 
        first = True

        for k in attrval:

            if k.startswith("_"):
                continue

            v = attrval[k]

            valtype = type(v).__name__

            if not first:
                comma = ","
            else:
                comma = ""   
                first = False

            if valtype == 'str' or valtype == 'unicode':
                output += comma + "\"" + k + "\":" + "\"" + v + "\""
            elif valtype == 'int': 
                output += comma + k + ":" + str(v)
            elif valtype == 'bool':
                if v:
                    output += comma + k + ":true"
                else:
                    output += comma + k + ":false"
                    
            else:
                result = tojson(None, v, plurals)
                if result:  
                    output += comma + "\"" + k + "\":" + result

        output += "}" 
 
        return output

    return output          



def get_payload_from_object(objname, obj, req_format, plurals, namespace=None, xmlstyle_as_elements=False):

        if plurals:
            LOG.debug(_("plurals dictionary contains: %s" % repr(plurals)))
        
        if req_format == "json": 
            payload= "{" + tojson(objname, obj, plurals) + "}"

        elif req_format == "xml":
            payload = "<?xml version=\"1.0\" ?>"
            payload += toxml(objname, obj, plurals, xmlnamespace=namespace, xmlstyle_as_elements=xmlstyle_as_elements, firstTime=True)
        else:
            payload = ""       
     
        return payload  



def get_dictionary_from_payload(payload, req_format, plurals):

        if req_format == "json": 
            obj = fromjson(payload, plurals)

        elif req_format == "xml":
            obj = fromxml(payload, plurals)
        else:
            obj = None       
     
        LOG.debug(_("Exiting get_dictionary_from_payload"))
 
        return obj

  


