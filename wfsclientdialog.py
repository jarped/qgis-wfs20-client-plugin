"""
/***************************************************************************
 WfsClientDialog
                                 A QGIS plugin
 WFS 2.0 Client
                             -------------------
        begin                : 2012-05-17
        copyright            : (C) 2012 by Juergen Weichand
        email                : juergen@weichand.de
        website              : http://www.weichand.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from PyQt4 import QtCore, QtGui
from PyQt4.QtNetwork import QHttp
from PyQt4 import QtXml, QtXmlPatterns
from ui_wfsclient import Ui_WfsClient
from qgis.core import *
from xml.etree import ElementTree 
import urllib
import urllib2 
import string
import random
import tempfile
import os
import os.path
import re
import wfs20lib
from metadataclientdialog import MetadataClientDialog

plugin_path = os.path.abspath(os.path.dirname(__file__))

class WfsClientDialog(QtGui.QDialog):

    def __init__(self, parent):
        QtGui.QDialog.__init__(self)
        # Set up the user interface from Designer.
        self.parent = parent
        self.ui = Ui_WfsClient()
        self.ui.setupUi(self)

        self.ui.frmExtent.show()
        self.ui.frmParameter.hide()
        self.ui.progressBar.setVisible(False)
        self.ui.cmdListStoredQueries.setVisible(False)

        # Load default onlineresource
        self.ui.txtUrl.setText(self.get_url())

        self.ui.txtUsername.setVisible(False)
        self.ui.txtPassword.setVisible(False)
        self.ui.lblUsername.setVisible(False)
        self.ui.lblPassword.setVisible(False)         

        self.parameter_lineedits = []
        self.parameter_labels = []

        self.settings = QtCore.QSettings()
        self.init_variables()

        self.onlineresource = ""
        self.vendorparameters = ""

        self.ui.lblMessage.setText("SRS is set to EPSG: {0}".format(str(self.parent.iface.mapCanvas().mapRenderer().destinationSrs().epsg())))
        self.ui.txtSrs.setText("EPSG:{0}".format(str(self.parent.iface.mapCanvas().mapRenderer().destinationSrs().epsg())))

        QtCore.QObject.connect(self.ui.cmdGetCapabilities, QtCore.SIGNAL("clicked()"), self.getCapabilities)
        QtCore.QObject.connect(self.ui.cmdListStoredQueries, QtCore.SIGNAL("clicked()"), self.listStoredQueries)
        QtCore.QObject.connect(self.ui.cmdGetFeature, QtCore.SIGNAL("clicked()"), self.getFeature)
        QtCore.QObject.connect(self.ui.cmdSaveUrl, QtCore.SIGNAL("clicked()"), self.save_url)
        QtCore.QObject.connect(self.ui.cmdMetadata, QtCore.SIGNAL("clicked()"), self.show_metadata)
        QtCore.QObject.connect(self.ui.chkExtent, QtCore.SIGNAL("clicked()"), self.update_extent_frame)
        QtCore.QObject.connect(self.ui.chkAuthentication, QtCore.SIGNAL("clicked()"), self.update_authentication)
        QtCore.QObject.connect(self.ui.cmbFeatureType, QtCore.SIGNAL("currentIndexChanged(int)"), self.update_ui)




    def init_variables(self):
        self.columnid = 0
        self.bbox = ""
        self.querytype = ""
        self.featuretypes = {}
        self.storedqueries = {}

    # Process GetCapabilities-Request
    def getCapabilities(self):
        self.init_variables()
        self.ui.cmdGetFeature.setEnabled(False);
        self.ui.cmbFeatureType.clear()
        self.ui.frmExtent.show()
        self.ui.frmParameter.hide()
        self.ui.chkExtent.setChecked(False)
        self.ui.txtExtentWest.setText("")
        self.ui.txtExtentEast.setText("")
        self.ui.txtExtentNorth.setText("")
        self.ui.txtExtentSouth.setText("")
        self.ui.cmdMetadata.setVisible(True)
        self.ui.lblCount.setVisible(True)
        self.ui.txtCount.setText("50")
        self.ui.txtCount.setVisible(True)
        self.ui.lblSrs.setVisible(True)
        self.ui.txtSrs.setText("EPSG:{0}".format(str(self.parent.iface.mapCanvas().mapRenderer().destinationSrs().epsg())))
        self.ui.txtSrs.setVisible(True)
        self.ui.txtFeatureTypeTitle.setVisible(False)
        self.ui.txtFeatureTypeDescription.setVisible(False)
        self.ui.lblInfo.setText("FeatureTypes")
        self.ui.lblMessage.setText("")

        try:
            self.onlineresource = self.ui.txtUrl.text().trimmed()
            if len(self.onlineresource) == 0:
                QtGui.QMessageBox.critical(self, "OnlineResource Error", "Not a valid OnlineResource!")
                return
            if "?" in self.onlineresource:
                request = "{0}{1}".format(self.onlineresource, self.fix_acceptversions(self.onlineresource, "&"))
            else: 
                request = "{0}{1}".format(self.onlineresource, self.fix_acceptversions(self.onlineresource, "?"))
            if self.ui.chkAuthentication.isChecked():
                self.setup_urllib2(request, self.ui.txtUsername.text().trimmed(), self.ui.txtPassword.text().trimmed())
            else:
                self.setup_urllib2(request, "", "")
            QgsMessageLog.logMessage(request, "Wfs20Client")
            response = urllib2.urlopen(request)
            buf = response.read()
        except urllib2.HTTPError, e:  
            QtGui.QMessageBox.critical(self, "HTTP Error", "HTTP Error: {0}".format(e.code))
            if e.code == 401:
                self.ui.chkAuthentication.setChecked(True)
                self.update_authentication()
        except urllib2.URLError, e:
            QtGui.QMessageBox.critical(self, "URL Error", "URL Error: {0}".format(e.reason))
        else:
            # process Response
            root = ElementTree.fromstring(buf)
            if self.is_wfs20_capabilties(root):
                # WFS 2.0 Namespace
                nswfs = "{http://www.opengis.net/wfs/2.0}"
                nsxlink = "{http://www.w3.org/1999/xlink}"
                nsows = "{http://www.opengis.net/ows/1.1}"
                # GetFeature OnlineResource
                for target in root.findall("{0}OperationsMetadata/{0}Operation".format(nsows)):
                    if target.get("name") == "GetFeature":                        
                        for subtarget in target.findall("{0}DCP/{0}HTTP/{0}Get".format(nsows)):
                            getfeatureurl = subtarget.get("{0}href".format(nsxlink))
                            if not "?" in getfeatureurl:
                                self.onlineresource = getfeatureurl
                            else:
                                self.onlineresource = getfeatureurl[:getfeatureurl.find("?")]
                                self.vendorparameters = getfeatureurl[getfeatureurl.find("?"):].replace("?", "&")
                for target in root.findall("{0}FeatureTypeList/{0}FeatureType".format(nswfs)):
                    for name in target.findall("{0}Name".format(nswfs)):
                        self.ui.cmbFeatureType.addItem(name.text,name.text)
                        featuretype = wfs20lib.FeatureType(name.text)                        
                        if ":" in name.text:
                            nsmap = self.get_namespace_map(buf)
                            for prefix in nsmap:
                                if prefix == name.text[:name.text.find(":")]:
                                    featuretype.setNamespace(nsmap[prefix])
                                    featuretype.setNamespacePrefix(prefix)
                                    break
                        for title in target.findall("{0}Title".format(nswfs)):
                            featuretype.setTitle(title.text)
                        for abstract in target.findall("{0}Abstract".format(nswfs)):
                            featuretype.setAbstract(abstract.text)
                        for metadata_url in target.findall("{0}MetadataURL".format(nswfs)):
                            featuretype.setMetadataUrl(metadata_url.get("{0}href".format(nsxlink)))
                        self.featuretypes[QtCore.QString(name.text)] = featuretype   
                        self.querytype="adhocquery"
            else:
                self.ui.lblMessage.setText("")        
            self.update_ui()

            # Lock
            self.ui.cmdGetCapabilities.setText("List FeatureTypes")
            self.ui.cmdListStoredQueries.setVisible(True)
            self.ui.chkAuthentication.setEnabled(False)
            self.ui.txtUrl.setEnabled(False)
            self.ui.txtUsername.setEnabled(False)
            self.ui.txtPassword.setEnabled(False)

   
    #Process ListStoredQueries-Request
    def listStoredQueries(self):
        self.init_variables()
        self.ui.cmdGetFeature.setEnabled(False);
        self.ui.cmbFeatureType.clear()
        self.ui.frmExtent.hide()
        self.ui.frmParameter.show()
        self.layout_reset()
        self.ui.cmdMetadata.setVisible(False)
        self.ui.lblCount.setVisible(False)
        self.ui.txtCount.setText("")
        self.ui.txtCount.setVisible(False)
        self.ui.lblSrs.setVisible(False)
        self.ui.txtSrs.setVisible(False)
        self.ui.txtFeatureTypeTitle.setVisible(False)
        self.ui.txtFeatureTypeDescription.setVisible(False)
        self.ui.lblInfo.setText("StoredQueries")
        self.ui.lblMessage.setText("")
        try:
            # self.onlineresource = self.ui.txtUrl.text().trimmed()
            if not self.onlineresource:
                QtGui.QMessageBox.critical(self, "OnlineResource Error", "Not a valid OnlineResource!")
                return
            if "?" in self.onlineresource:
                request = "{0}&service=WFS&version=2.0.0&request=DescribeStoredQueries".format(self.onlineresource)
            else:
                request = "{0}?service=WFS&version=2.0.0&request=DescribeStoredQueries".format(self.onlineresource)
            if self.ui.chkAuthentication.isChecked():
                self.setup_urllib2(request, self.ui.txtUsername.text().trimmed(), self.ui.txtPassword.text().trimmed())
            else:
                self.setup_urllib2(request, "", "")
            QgsMessageLog.logMessage(request, "Wfs20Client")
            response = urllib2.urlopen(request)
            buf = response.read()
        except urllib2.HTTPError, e:  
            QtGui.QMessageBox.critical(self, "HTTP Error", "HTTP Error: {0}".format(e.code))
            if e.code == 401:
                self.ui.chkAuthentication.setChecked(True)
                self.update_authentication()
        except urllib2.URLError, e:
            QtGui.QMessageBox.critical(self, "URL Error", "URL Error: {0}".format(e.reason))
        else:
            # process Response
            root = ElementTree.fromstring(buf)
            # WFS 2.0 Namespace
            namespace = "{http://www.opengis.net/wfs/2.0}"
            # check correct Rootelement
            if root.tag == "{0}DescribeStoredQueriesResponse".format(namespace):  
                for target in root.findall("{0}StoredQueryDescription".format(namespace)):
                    self.ui.cmbFeatureType.addItem(target.get("id"),target.get("id"))
                    lparameter = []
                    for parameter in target.findall("{0}Parameter".format(namespace)):
                        lparameter.append(wfs20lib.StoredQueryParameter(parameter.get("name"), parameter.get("type")))                     
                    storedquery = wfs20lib.StoredQuery(QtCore.QString(target.get("id")), lparameter)
                    for title in target.findall("{0}Title".format(namespace)):
                        storedquery.setTitle(title.text)
                    for abstract in target.findall("{0}Abstract".format(namespace)):
                        storedquery.setAbstract(abstract.text)
                    self.storedqueries[QtCore.QString(target.get("id"))] = storedquery
                    self.querytype="storedquery" #R
            else:
                QtGui.QMessageBox.critical(self, "Error", "Not a valid DescribeStoredQueries-Response!")
            self.update_ui()


    # Process GetFeature-Request
    def getFeature(self):
        self.ui.lblMessage.setText("Please wait while downloading!")
        if self.querytype == "storedquery":
            query_string = "?service=WFS&request=GetFeature&version=2.0.0&STOREDQUERY_ID={0}".format(self.ui.cmbFeatureType.currentText())
            storedquery = self.storedqueries[self.ui.cmbFeatureType.currentText()]
            lparameter = storedquery.getStoredQueryParameterList()
            for i in range(len(lparameter)):
                if not lparameter[i].isValidValue(self.parameter_lineedits[i].text()):
                    QtGui.QMessageBox.critical(self, "Validation Error", lparameter[i].getName() + ": Value validation failed!")
                    self.ui.lblMessage.setText("")
                    return
                query_string+= "&{0}={1}".format(lparameter[i].getName(),self.parameter_lineedits[i].text())
        else :
            # FIX
            featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]
            if len(self.bbox) < 1:                
                query_string = "?service=WFS&request=GetFeature&version=2.0.0&srsName={0}&typeNames={1}".format(self.ui.txtSrs.text(), self.ui.cmbFeatureType.currentText())
            else: 
                query_string = "?service=WFS&request=GetFeature&version=2.0.0&srsName={0}&typeNames={1}&bbox={2}".format(self.ui.txtSrs.text(), self.ui.cmbFeatureType.currentText(), self.bbox)

            if len(featuretype.getNamespace()) > 0 and len(featuretype.getNamespacePrefix()) > 0:
                #query_string += "&namespace=xmlns({0}={1})".format(featuretype.getNamespacePrefix(), urllib.quote(featuretype.getNamespace(),""))
                query_string += "&namespaces=xmlns({0},{1})".format(featuretype.getNamespacePrefix(), urllib.quote(featuretype.getNamespace(),""))
            
            if len(self.ui.txtCount.text()) > 0:
                query_string+= "&count={0}".format(self.ui.txtCount.text())
            # /FIX
                
        query_string+=self.vendorparameters
        QgsMessageLog.logMessage(self.onlineresource + query_string, "Wfs20Client")

        self.httpGetId = 0
        self.httpRequestAborted = False
        
        self.setup_qhttp()
        self.http.requestFinished.connect(self.httpRequestFinished)
        self.http.dataReadProgress.connect(self.updateDataReadProgress)
        self.http.responseHeaderReceived.connect(self.readResponseHeader)
        self.http.authenticationRequired.connect(self.authenticationRequired)
        
        layername="wfs{0}".format(''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(6)))
        self.downloadFile(self.onlineresource, query_string, self.get_temppath("{0}.gml".format(layername)))

    
    """
    ############################################################################################################################
    # UI
    ############################################################################################################################
    """

    # UI: Update Parameter-Frame
    def update_ui(self):      
                      
        if self.querytype == "adhocquery":
            featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]

            if featuretype.getTitle():
                if len(featuretype.getTitle()) > 0:
                    self.ui.txtFeatureTypeTitle.setVisible(True)
                    self.ui.txtFeatureTypeTitle.setPlainText(featuretype.getTitle())
                else:
                    self.ui.txtFeatureTypeTitle.setVisible(False)
            else: 
                self.ui.txtFeatureTypeTitle.setVisible(False)

            if featuretype.getAbstract():
                if len(featuretype.getAbstract()) > 0:
                    self.ui.txtFeatureTypeDescription.setVisible(True)
                    self.ui.txtFeatureTypeDescription.setPlainText(featuretype.getAbstract())
                else:
                    self.ui.txtFeatureTypeDescription.setVisible(False)
            else: 
                self.ui.txtFeatureTypeDescription.setVisible(False)

            self.show_metadata_button(True)

            self.ui.cmdGetFeature.setEnabled(True);
            self.ui.lblMessage.setText("")

        if self.querytype == "storedquery":
            storedquery = self.storedqueries[self.ui.cmbFeatureType.currentText()]

            if storedquery.getTitle():
                if len(storedquery.getTitle()) > 0:
                    self.ui.txtFeatureTypeTitle.setVisible(True)
                    self.ui.txtFeatureTypeTitle.setPlainText(storedquery.getTitle())
                else:
                    self.ui.txtFeatureTypeTitle.setVisible(False)
            else: 
                self.ui.txtFeatureTypeTitle.setVisible(False)
            if storedquery.getAbstract():
                if len(storedquery.getAbstract()) > 0:
                    self.ui.txtFeatureTypeDescription.setVisible(True)
                    self.ui.txtFeatureTypeDescription.setPlainText(storedquery.getAbstract())
                else:
                    self.ui.txtFeatureTypeDescription.setVisible(False)
            else: 
                self.ui.txtFeatureTypeDescription.setVisible(False)

            self.ui.cmdGetFeature.setEnabled(True)
            self.ui.lblMessage.setText("")
            self.layout_reset()
            for parameter in storedquery.getStoredQueryParameterList(): 
                self.layout_add_parameter(parameter)


    # UI: Update Extent-Frame
    def update_extent_frame(self):
        if self.ui.chkExtent.isChecked():
            canvas=self.parent.iface.mapCanvas()
            ext=canvas.extent()
            self.ui.txtExtentWest.setText(QtCore.QString('%s'%ext.xMinimum()))                                                                                                                                                                                                                                                                                                                                                                                                  
            self.ui.txtExtentEast.setText(QtCore.QString('%s'%ext.xMaximum()))                                                                                                                                                                                                                                                                                                                                                                                                  
            self.ui.txtExtentNorth.setText(QtCore.QString('%s'%ext.yMaximum()))                                                                                                                                                                                                                                                                                                                                                                                                  
            self.ui.txtExtentSouth.setText(QtCore.QString('%s'%ext.yMinimum()))
            self.bbox=QtCore.QString('%s'%ext.xMinimum()) + "," + QtCore.QString('%s'%ext.yMinimum()) + "," + QtCore.QString('%s'%ext.xMaximum()) + "," + QtCore.QString('%s'%ext.yMaximum()) + ",{0}".format(self.ui.txtSrs.text())
        else: 
            self.ui.txtExtentWest.setText("")
            self.ui.txtExtentEast.setText("")
            self.ui.txtExtentNorth.setText("")
            self.ui.txtExtentSouth.setText("")
            self.bbox=""

    # UI: Update Main-Frame / Enable|Disable Authentication
    def update_authentication(self):
        if not self.ui.chkAuthentication.isChecked():
            self.ui.frmMain.setGeometry(QtCore.QRect(10,90,501,551))
            self.ui.txtUsername.setVisible(False)
            self.ui.txtPassword.setVisible(False)
            self.ui.lblUsername.setVisible(False)
            self.ui.lblPassword.setVisible(False)
            self.resize(516, 648)
        else:
            self.ui.frmMain.setGeometry(QtCore.QRect(10,150,501,551))
            self.ui.txtUsername.setVisible(True)
            self.ui.txtPassword.setVisible(True)
            self.ui.lblUsername.setVisible(True)
            self.ui.lblPassword.setVisible(True)
            self.resize(516, 704)

  
    # GridLayout reset (StoredQueries)
    def layout_reset(self):
        for qlabel in self.parameter_labels:
            self.ui.gridLayout.removeWidget(qlabel)
            qlabel.setParent(None) # http://www.riverbankcomputing.com/pipermail/pyqt/2008-March/018803.html

        for qlineedit in self.parameter_lineedits:
            self.ui.gridLayout.removeWidget(qlineedit)
            qlineedit.setParent(None) # http://www.riverbankcomputing.com/pipermail/pyqt/2008-March/018803.html
        
        del self.parameter_labels[:]
        del self.parameter_lineedits[:]
        self.columnid = 0


    # GridLayout addParameter (StoredQueries)
    def layout_add_parameter(self, storedqueryparameter):
        qlineedit = QtGui.QLineEdit()
        qlabelname = QtGui.QLabel()
        qlabelname.setText(storedqueryparameter.getName())
        qlabeltype = QtGui.QLabel()
        qlabeltype.setText(storedqueryparameter.getType().replace("xsd:", ""))
        self.ui.gridLayout.addWidget(qlabelname, self.columnid, 0)
        self.ui.gridLayout.addWidget(qlineedit, self.columnid, 1)
        self.ui.gridLayout.addWidget(qlabeltype, self.columnid, 2)
        self.columnid = self.columnid + 1
        self.parameter_labels.append(qlabelname)
        self.parameter_labels.append(qlabeltype)
        self.parameter_lineedits.append(qlineedit)
        # newHeight = self.geometry().height() + 21
        # self.resize(self.geometry().width(), newHeight)
  
 
    def lock_ui(self):
        self.ui.cmdGetCapabilities.setEnabled(False)
        self.ui.cmdListStoredQueries.setEnabled(False)
        self.ui.cmdGetFeature.setEnabled(False)
        self.ui.cmdSaveUrl.setEnabled(False)
        self.ui.cmbFeatureType.setEnabled(False)
        self.show_metadata_button(False)

    def unlock_ui(self):
        self.ui.cmdGetCapabilities.setEnabled(True)
        self.ui.cmdListStoredQueries.setEnabled(True)
        self.ui.cmdGetFeature.setEnabled(True)
        self.ui.cmdSaveUrl.setEnabled(True)
        self.ui.cmbFeatureType.setEnabled(True)
        self.show_metadata_button(True)

    def show_metadata_button(self, enabled):
        if enabled:
            if self.querytype == "adhocquery":
                featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]
                if featuretype.getMetadataUrl():
                    if len(featuretype.getMetadataUrl()) > 0:
                        self.ui.cmdMetadata.setEnabled(True)
                    else:
                        self.ui.cmdMetadata.setEnabled(False)
                else: 
                    self.ui.cmdMetadata.setEnabled(False)
        else:
            self.ui.cmdMetadata.setEnabled(False)

    def show_metadata(self):
        featuretype = self.featuretypes[self.ui.cmbFeatureType.currentText()]
        xslfilename = os.path.join(plugin_path, "iso19139jw.xsl")

        html = self.xsl_transform(featuretype.getMetadataUrl(), xslfilename)

        if html:
            # create and show the dialog
            dlg = MetadataClientDialog()
            dlg.ui.wvMetadata.setHtml(html)
            # show the dialog
            dlg.show()
            result = dlg.exec_()
            # See if OK was pressed
            if result == 1:
                # do something useful (delete the line containing pass and
                # substitute with your code
                pass
        else:
            QtGui.QMessageBox.critical(self, "Metadata Error", "Unable to read the Metadata")

 

    """
    ############################################################################################################################
    # UTIL
    ############################################################################################################################
    """
    def save_url(self):
        self.save_tempfile("defaultwfs.txt", str(self.ui.txtUrl.text().trimmed()))
        QtGui.QMessageBox.information(self.parent.iface.mainWindow(),"Info", "Successfully saved OnlineResource!" )

    def get_url(self):
        try:
            tmpdir = os.path.join(tempfile.gettempdir(),'wfs20client')
            tmpfile= os.path.join(tmpdir, "defaultwfs.txt")
            fobj=open(tmpfile,'r')
            url = fobj.readline()
            fobj.close()
            return url
        except IOError, e:
            return "http://geoserv.weichand.de:8080/geoserver/wfs"

    def get_temppath(self, filename):
        tmpdir = os.path.join(tempfile.gettempdir(),'wfs20client')
        if not os.path.exists(tmpdir):
            os.makedirs(tmpdir)
        tmpfile= os.path.join(tmpdir, filename)
        return tmpfile

    def save_tempfile(self, filename, content):
        tmpdir = os.path.join(tempfile.gettempdir(),'wfs20client')
        if not os.path.exists(tmpdir):
            os.makedirs(tmpdir)
        tmpfile= os.path.join(tmpdir, filename)
        fobj=open(tmpfile,'wb')
        fobj.write(content)
        fobj.close()  
        return tmpfile

    # Receive Proxy from QGIS-Settings
    def getProxy(self):
        if self.settings.value("/proxy/proxyEnabled").toString() == "true":
           proxy = "{0}:{1}".format(self.settings.value("/proxy/proxyHost").toString(), self.settings.value("/proxy/proxyPort").toString())
           if proxy.startswith("http://"):
               return proxy
           else:
               return proxy
        else: 
            return ""
    
    # Setup urllib2 (Proxy)
    def setup_urllib2(self, request, username, password):
        # with Authentication
        if username and len(username) > 0:
            if password and len(password) > 0:
                password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
                password_mgr.add_password(None, request, username, password)
                auth_handler = urllib2.HTTPBasicAuthHandler(password_mgr)

                if not self.getProxy() == "":
                    proxy_handler = urllib2.ProxyHandler({"http" : self.getProxy()})                    
                else: 
                    proxy_handler = urllib2.ProxyHandler({})
                opener = urllib2.build_opener(proxy_handler, auth_handler)
                urllib2.install_opener(opener)  

        # without Authentication    
        else:
            if not self.getProxy() == "":
                proxy_handler = urllib2.ProxyHandler({"http" : self.getProxy()})
            else: 
                proxy_handler = urllib2.ProxyHandler({})
            opener = urllib2.build_opener(proxy_handler)
            urllib2.install_opener(opener)

    # Setup Qhttp (Proxy)
    def setup_qhttp(self):
        self.http = QHttp(self)
        if not self.getProxy() == "":
            self.http.setProxy(QgsNetworkAccessManager.instance().fallbackProxy()) # Proxy       
        

    # XSL Transformation
    def xsl_transform(self, url, xslfilename):
        try:
            self.setup_urllib2(url, "", "")
            response = urllib2.urlopen(url)
            buf = response.read()
        except urllib2.HTTPError, e:  
            QtGui.QMessageBox.critical(self, "HTTP Error", "HTTP Error: {0}".format(e.code))
        except urllib2.URLError, e:
            QtGui.QMessageBox.critical(self, "URL Error", "URL Error: {0}".format(e.reason))
        else:
           # load xslt
           xslt_file = QtCore.QFile(xslfilename)
           xslt_file.open(QtCore.QIODevice.ReadOnly)
           xslt = QtCore.QString(xslt_file.readAll())
           xslt_file.close()
 
           # load xml
           xml_source = QtCore.QString.fromUtf8(buf)

           # xslt
           qry = QtXmlPatterns.QXmlQuery(QtXmlPatterns.QXmlQuery.XSLT20)
           qry.setFocus(xml_source)
           qry.setQuery(xslt)

           array = QtCore.QByteArray()
           buf = QtCore.QBuffer(array)
           buf.open(QtCore.QIODevice.WriteOnly)
           qry.evaluateTo(buf)
           xml_target = QtCore.QString.fromUtf8(array)
           return xml_target


    # WFS 2.0 UTILS

    # check for OWS-Exception
    def is_exception(self, root):
        for namespace in ["{http://www.opengis.net/ows}", "{http://www.opengis.net/ows/1.1}"]:
        # check correct Rootelement
            if root.tag == "{0}ExceptionReport".format(namespace):  
                for exception in root.findall("{0}Exception".format(namespace)):
                    for exception_text in exception.findall("{0}ExceptionText".format(namespace)):
                        QtGui.QMessageBox.critical(self, "OWS Exception", "OWS Exception returned from the WFS:<br>"+ str(exception_text.text))
                        self.ui.lblMessage.setText("")
                return True
        return False


    # check for correct WFS version (only WFS 2.0 supported)
    def is_wfs20_capabilties(self, root):
        if self.is_exception(root):
            return False
        if root.tag == "{0}WFS_Capabilities".format("{http://www.opengis.net/wfs/2.0}"):  
            return True
        if root.tag == "{0}WFS_Capabilities".format("{http://www.opengis.net/wfs}"):  
            QtGui.QMessageBox.warning(self, "Wrong WFS Version", "This Plugin has dedicated support for WFS 2.0!")
            self.ui.lblMessage.setText("")
            return False
        QtGui.QMessageBox.critical(self, "Error", "Not a valid WFS GetCapabilities-Response!")
        self.ui.lblMessage.setText("")
        return False


    # Check for empty GetFeature result
    def is_empty_response(self, root):
        if root.get("numberReturned") == "unknown":
            return True
        if root.get("numberReturned") == "0":
            return True
        return False
        

    # Hack to fix version/acceptversions Request-Parameter
    def fix_acceptversions(self, onlineresource, connector):
        return "{0}service=WFS&acceptversions=2.0.0&request=GetCapabilities".format(connector)


    # Determine namespaces in the capabilities (including non-used)
    def get_namespace_map(self, xml):
        nsmap = {}
        for i in [m.start() for m in re.finditer('xmlns:', xml)]:
            j = i + 6
            prefix = xml[j:xml.find("=", j)]
            k = xml.find("\"", j)
            uri = xml[k + 1:xml.find("\"", k + 1)]

            prefix = prefix.strip()
            # uri = uri.replace("\"","")
            uri = uri.strip()
            # text+= prefix + " " + uri + "\n"
 
            nsmap[prefix] = uri
        return nsmap


    #############################################################################################################
    # QHttp GetFeature-Request - http://stackoverflow.com/questions/6852038/threading-in-pyqt4
    #############################################################################################################

    # QHttp Slot
    def downloadFile(self, onlineResource, queryString, fileName):
        self.lock_ui()
        url = QtCore.QUrl(onlineResource)

        if QtCore.QFile.exists(fileName):
            QtCore.QFile.remove(fileName)

        self.outFile = QtCore.QFile(fileName)
        if not self.outFile.open(QtCore .QIODevice.WriteOnly):
            QtGui.QMessageBox.information(self, 'Error',
                    'Unable to save the file %s: %s.' % (fileName, self.outFile.errorString()))
            self.outFile = None
            return

        mode = QHttp.ConnectionModeHttp
        port = url.port()
        if port == -1:
            port = 0
        self.http.setHost(url.host(), mode, port)
        self.httpRequestAborted = False
        # Download the file.
        self.ui.progressBar.setVisible(True)
        self.httpGetId = self.http.get(url.path() + queryString, self.outFile)

    # Currently unused
    def cancelDownload(self):
        self.httpRequestAborted = True
        self.http.abort()
        self.close()

        self.ui.progressBar.setMaximum(1)
        self.ui.progressBar.setValue(0)
        self.unlock_ui()

    # QHttp Slot
    def httpRequestFinished(self, requestId, error):
        if requestId != self.httpGetId:
            return

        if self.httpRequestAborted:
            if self.outFile is not None:
                self.outFile.close()
                self.outFile.remove()
                self.outFile = None
            return

        self.outFile.close()

        self.ui.progressBar.setMaximum(1)
        self.ui.progressBar.setValue(1)

        if error:
            self.outFile.remove()
            QtGui.QMessageBox.critical(self, "Error", "Download failed: %s." % self.http.errorString())
        else:      
            # Parse and check only small files
            if os.path.getsize(str(self.outFile.fileName())) < 5000:
                root = ElementTree.parse(str(self.outFile.fileName())).getroot()
                if not self.is_exception(root):                 
                    if not self.is_empty_response(root):
                        self.load_vector_layer(str(self.outFile.fileName()), self.ui.cmbFeatureType.currentText())
                    else:
                        QtGui.QMessageBox.information(self, "Information", "0 Features returned!")
                        self.ui.lblMessage.setText("")
            else: 
                self.load_vector_layer(str(self.outFile.fileName()), self.ui.cmbFeatureType.currentText())

        self.ui.progressBar.setMaximum(1)
        self.ui.progressBar.setValue(0)
        self.unlock_ui()
    
    # QHttp Slot
    def readResponseHeader(self, responseHeader):
        # Check for genuine error conditions.
        if responseHeader.statusCode() not in (200, 300, 301, 302, 303, 307):
            QtGui.QMessageBox.critical(self, 'Error',
                    'Download failed: %s.' % responseHeader.reasonPhrase())
            self.ui.lblMessage.setText("")
            self.httpRequestAborted = True
            self.http.abort()

    def updateDataReadProgress(self, bytesRead, totalBytes):
        if self.httpRequestAborted:
            return
        self.ui.progressBar.setMaximum(totalBytes)
        self.ui.progressBar.setValue(bytesRead)
        self.ui.lblMessage.setText("Please wait while downloading - {0} Bytes downloaded!".format(str(bytesRead)))

    # QHttp Slot
    def authenticationRequired(self, hostName, _, authenticator):
        authenticator.setUser(self.ui.txtUsername.text().trimmed())
        authenticator.setPassword(self.ui.txtPassword.text().trimmed())

    def load_vector_layer(self, filename, layername):
        vlayer = QgsVectorLayer(filename, layername, "ogr")    
        vlayer.setProviderEncoding("UTF-8") #Ignore System Encoding --> TODO: Use XML-Header        
        if not vlayer.isValid():
            QtGui.QMessageBox.critical(self, "Error", "Response is not a valid QGIS-Layer!")
            self.ui.lblMessage.setText("")
        else: 
            self.ui.lblMessage.setText("")
            QgsMapLayerRegistry.instance().addMapLayer(vlayer)
            self.parent.iface.zoomToActiveLayer()

