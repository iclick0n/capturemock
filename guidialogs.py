#!/usr/bin/env python

import gtk
import gobject

import guiplugins, plugins, os, string, time, sys, locale
from gtkusecase import ScriptEngine, TreeModelIndexer

def setupScriptEngine(engine):
    global scriptEngine, guilog
    scriptEngine = engine
    from guiplugins import guilog

def destroyDialog(dialog, *args):
    dialog.destroy()

def createDialogMessage(message, stockIcon, scrollBars=False):
    buffer = gtk.TextBuffer()
    buffer.set_text(message)
    textView = gtk.TextView(buffer)
    textView.set_editable(False)
    textView.set_cursor_visible(False)
    textView.set_left_margin(5)
    textView.set_right_margin(5)
    hbox = gtk.HBox()
    imageBox = gtk.VBox()
    imageBox.pack_start(gtk.image_new_from_stock(stockIcon, gtk.ICON_SIZE_DIALOG), expand=False)
    hbox.pack_start(imageBox, expand=False)
    scrolledWindow = gtk.ScrolledWindow()
    # What we would like is that the dialog expands without scrollbars
    # until it reaches some maximum size, and then adds scrollbars. At
    # the moment I cannot make this happen without setting a fixed window
    # size, so I'll set the scrollbar policy to never instead.
    if scrollBars:
        scrolledWindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
    else:
        scrolledWindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_NEVER)
    scrolledWindow.add(textView)
    scrolledWindow.set_shadow_type(gtk.SHADOW_IN)
    hbox.pack_start(scrolledWindow, expand=True, fill=True)
    alignment = gtk.Alignment()
    alignment.set_padding(5, 5, 0, 5)
    alignment.add(hbox)
    return alignment

def showErrorDialog(message, parent=None):
    guilog.info("ERROR: " + message)
    dialog = gtk.Dialog("TextTest Error", parent, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
    dialog.set_modal(True)
    dialog.vbox.pack_start(createDialogMessage(message, gtk.STOCK_DIALOG_ERROR), expand=True, fill=True)
    scriptEngine.connect("agree to texttest message", "response", dialog, destroyDialog, gtk.RESPONSE_ACCEPT)
    dialog.show_all()
    dialog.action_area.get_children()[len(dialog.action_area.get_children()) - 1].grab_focus()

def showWarningDialog(message, parent=None):
    guilog.info("WARNING: " + message)
    dialog = gtk.Dialog("TextTest Warning", parent, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
    dialog.set_modal(True)
    dialog.vbox.pack_start(createDialogMessage(message, gtk.STOCK_DIALOG_WARNING), expand=True, fill=True)
    scriptEngine.connect("agree to texttest message", "response", dialog, destroyDialog, gtk.RESPONSE_ACCEPT)
    dialog.show_all()
    dialog.action_area.get_children()[len(dialog.action_area.get_children()) - 1].grab_focus()

def showInformationDialog(message, parent=None):
    guilog.info("INFORMATION: " + message)
    dialog = gtk.Dialog("TextTest Information", parent, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
    dialog.set_modal(True)
    dialog.vbox.pack_start(createDialogMessage(message, gtk.STOCK_DIALOG_INFO), expand=True, fill=True)
    scriptEngine.connect("agree to texttest message", "response", dialog, destroyDialog, gtk.RESPONSE_ACCEPT)
    dialog.show_all()
    dialog.action_area.get_children()[len(dialog.action_area.get_children()) - 1].grab_focus()

class DoubleCheckDialog:
    def __init__(self, message, yesMethod, noMethod=None, parent=None):
        self.dialog = gtk.Dialog("TextTest Query", parent, flags=gtk.DIALOG_MODAL)
        self.yesMethod = yesMethod
        self.noMethod = noMethod
        guilog.info("QUERY: " + message)
        noButton = self.dialog.add_button(gtk.STOCK_NO, gtk.RESPONSE_NO)
        yesButton = self.dialog.add_button(gtk.STOCK_YES, gtk.RESPONSE_YES)
        self.dialog.set_modal(True)
        self.dialog.vbox.pack_start(createDialogMessage(message, gtk.STOCK_DIALOG_QUESTION), expand=True, fill=True)
        # ScriptEngine cannot handle different signals for the same event (e.g. response
        # from gtk.Dialog), so we connect the individual buttons instead ...
        scriptEngine.connect("answer no to texttest query", "clicked", noButton, self.respond, gtk.RESPONSE_NO, False)
        scriptEngine.connect("answer yes to texttest query", "clicked", yesButton, self.respond, gtk.RESPONSE_YES, True)
        self.dialog.show_all()
        self.dialog.set_default_response(gtk.RESPONSE_NO)
        self.dialog.action_area.get_children()[len(self.dialog.action_area.get_children()) - 1].grab_focus()

    def respond(self, button, saidYes, *args):
        self.dialog.hide()
        self.dialog.response(gtk.RESPONSE_NONE)
        if saidYes:
            self.yesMethod()
        elif self.noMethod:
            self.noMethod()

#
# A skeleton for a dialog which can replace the 'tab options' of
# today's actions. I think it should be possible to customize the
# look of the dialog, so I'll let each subclass create its widgets,
# rather than follow the TextTestGUI way to centrally decide the
# option tab page layout. I think this will only add a minor overhead,
# but will make it much easier to make the dialogs look nice.
# 
class ActionConfirmationDialog:
    def __init__(self, parent, okMethod, cancelMethod, plugin):
        self.parent = parent
        self.plugin = plugin
        self.okMethod = okMethod
        self.cancelMethod = cancelMethod
        self.dialog = gtk.Dialog(self.plugin.getScriptTitle(None), parent, flags=gtk.DIALOG_MODAL)
        self.createButtons()
        self.dialog.set_modal(True)
        
    def createButtons(self):
        self.cancelButton = self.dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        self.okButton = self.dialog.add_button(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT)       
        scriptEngine.connect("press cancel", "clicked", self.cancelButton, self.respond, gtk.RESPONSE_CANCEL, False)
        scriptEngine.connect("press ok", "clicked", self.okButton, self.respond, gtk.RESPONSE_ACCEPT, True)

    def respond(self, button, saidOK, *args):
        self.dialog.hide()
        self.dialog.response(gtk.RESPONSE_NONE)
        if saidOK:
            self.okMethod()
        else:
            self.cancelMethod()

    def run(self):
        self.addContents()
        self.dialog.show_all()
        
class SaveSelectionDialog(ActionConfirmationDialog):
    def __init__(self, parent, okMethod, cancelMethod, plugin):
        self.fileChooser = gtk.FileChooserWidget(gtk.FILE_CHOOSER_ACTION_SAVE)
        self.plugin = plugin
        self.folders, defaultFolder = self.plugin.getDirectories()
        self.startFolder = os.getcwd() # Just to make sure we always have some dir ...
        if defaultFolder and os.path.isdir(os.path.abspath(defaultFolder)):
            self.startFolder = os.path.abspath(defaultFolder)
        self.enableOptions = self.plugin.dialogEnableOptions()
        ActionConfirmationDialog.__init__(self, parent, okMethod, cancelMethod, plugin)
        self.dialog.set_modal(True)
        self.dialog.set_default_response(gtk.RESPONSE_ACCEPT)

    def createButtons(self):
        self.cancelButton = self.dialog.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        self.okButton = self.dialog.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT)
        scriptEngine.registerFileChooser("choose to save in file ", self.fileChooser, self.okButton, self.folders)
        scriptEngine.connect("press cancel", "clicked", self.cancelButton, self.respond, gtk.RESPONSE_CANCEL, False)
        scriptEngine.connect("press save", "clicked", self.okButton, self.respond, gtk.RESPONSE_ACCEPT, True)

    def addContents(self):
        alignment = gtk.Alignment()
        alignment.set(1.0, 1.0, 1.0, 1.0)
        alignment.set_padding(5, 5, 5, 5)
        vbox = gtk.VBox()
        alignment.add(vbox)
        self.dialog.vbox.pack_start(alignment, expand=True, fill=True)

        # We want a filechooser dialog to let the user choose where, and
        # with which name, to save the selection.
        self.fileChooser.set_current_folder(self.startFolder)
        for i in xrange(len(self.folders) - 1, -1, -1):
            self.fileChooser.add_shortcut_folder(self.folders[i][1])
        self.fileChooser.set_local_only(True)
        vbox.pack_start(self.fileChooser, expand=True, fill=True)

        # In the static GUI case, we also want radiobuttons specifying 
        # whether we want to save the actual tests, or the selection criteria.
        frame = gtk.Frame("Save")
        frameBox = gtk.VBox()
        self.radio1 = gtk.RadioButton(label="_List of selected tests", use_underline=True)
        self.radio2 = gtk.RadioButton(self.radio1, label="C_riteria entered in the Selection tab\n(Might not match current selection, if it has been modified)", use_underline=True) # Letting C be mnemonic conflicts with cancel button ...
        scriptEngine.registerToggleButton(self.radio1, "choose to save list of selected tests")
        scriptEngine.registerToggleButton(self.radio2, "choose to save selection criteria")
        frameBox.pack_start(self.radio1)
        frameBox.pack_start(self.radio2)
        frame.add(frameBox)
        if not self.enableOptions:
            frame.set_sensitive(False)
        self.fileChooser.set_extra_widget(frame)

    def run(self):
        self.addContents()
        self.dialog.show_all()

    def respond(self, button, saidOK, *args):
        if saidOK:
            if not self.fileChooser.get_filename():
                self.fileChooser.set_current_name("filename_mandatory")
                return
            if os.path.isdir(self.fileChooser.get_filename()):
                self.fileChooser.set_current_folder(self.fileChooser.get_filename())
                self.fileChooser.set_current_name("filename_mandatory")
                return                
            if os.path.exists(self.fileChooser.get_filename()):
                confirmation = DoubleCheckDialog("\nThe file \n" + self.fileChooser.get_filename() + "\nalready exists.\n\nDo you want to overwrite it?\n", lambda : self.setOptionsAndExit(saidOK))
            else:
                self.setOptionsAndExit(saidOK)
        else:
            self.doExit(saidOK)

    def setOptionsAndExit(self, saidOK):
        # Transfer file name and options back to plugin
        self.plugin.fileName = self.fileChooser.get_filename()
        if self.enableOptions:
            self.plugin.saveTestList = self.radio1.get_active()
        self.doExit(saidOK)
        
    def doExit(self, saidOK):
        self.dialog.hide()
        self.dialog.response(gtk.RESPONSE_NONE)
        if saidOK:
            self.okMethod()
        else:
            self.cancelMethod()
            
class RenameDialog(ActionConfirmationDialog):
    def __init__(self, parent, okMethod, cancelMethod, plugin):
        ActionConfirmationDialog.__init__(self, parent, okMethod, cancelMethod, plugin)
        self.dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        
    def addContents(self):        
        alignment = gtk.Alignment()
        alignment.set(1.0, 1.0, 1.0, 1.0)
        alignment.set_padding(5, 5, 5, 5)
        vbox = gtk.VBox()
        alignment.add(vbox)
        self.dialog.vbox.pack_start(alignment, expand=True, fill=True)

        header = gtk.Label()
        header.set_markup("<b>" + plugins.convertForMarkup(self.plugin.oldName) + "</b>")
        vbox.pack_start(header)
        hbox2 = gtk.HBox()
        hbox2.pack_start(gtk.Label("\nNew name:"), expand=False, fill=False)        
        vbox.pack_start(hbox2)
        self.entry = gtk.Entry()
        self.entry.set_text(self.plugin.newName)
        scriptEngine.registerEntry(self.entry, "enter new name ")
        vbox.pack_start(self.entry)
        hbox3 = gtk.HBox()
        hbox3.pack_start(gtk.Label("\nNew description:"), expand=False, fill=False)
        vbox.pack_start(hbox3)
        self.descriptionEntry = gtk.Entry()
        self.descriptionEntry.set_text(self.plugin.newDescription)
        scriptEngine.registerEntry(self.descriptionEntry, "enter new description ")
        vbox.pack_start(self.descriptionEntry)
        
    def respond(self, button, saidOK, *args):
        if saidOK:
            self.plugin.newName = self.entry.get_text()
            self.plugin.newDescription = self.descriptionEntry.get_text()
            message, error = self.plugin.checkNewName()
            if error:
                showErrorDialog(message, self.dialog)
                return
            elif message:
                dialog = DoubleCheckDialog(message, lambda: ActionConfirmationDialog.respond(self, button, saidOK, *args))
                return
        ActionConfirmationDialog.respond(self, button, saidOK, *args)
        
# It's a bit unfortunate that this has to be here, but unfortunately texttestgui
# cannot load dialogs from matador without some additional work. Also, having it
# here avoids matador importing guidialogs, and hence gtk.
class CreatePerformanceReportDialog(ActionConfirmationDialog):
    def __init__(self, parent, okMethod, cancelMethod, plugin):
        ActionConfirmationDialog.__init__(self, parent, okMethod, cancelMethod, plugin)
        self.dialog.set_default_response(gtk.RESPONSE_ACCEPT)

    def addContents(self):
        # A simple entry for the path, and one for the versions ...
        self.dirEntry = gtk.Entry()
        self.versionsEntry = gtk.Entry()
        self.dirEntry.set_text(self.plugin.rootDir)
        self.versionsEntry.set_text(",".join(self.plugin.versions).rstrip(","))
        
        table = gtk.Table(2, 2, homogeneous=False)
        table.set_row_spacings(1)
        table.attach(gtk.Label("Save in directory:"), 0, 1, 0, 1, xoptions=gtk.FILL, xpadding=1)
        table.attach(gtk.Label("Compare versions:"), 0, 1, 1, 2, xoptions=gtk.FILL, xpadding=1)
        table.attach(self.dirEntry, 1, 2, 0, 1)
        table.attach(self.versionsEntry, 1, 2, 1, 2)
        scriptEngine.registerEntry(self.dirEntry, "choose directory ")
        scriptEngine.registerEntry(self.versionsEntry, "choose versions ")
        table.show_all()
        self.dialog.vbox.pack_start(table, expand = True, fill = True)
        
    def respond(self, button, saidOK, *args):
        if saidOK:
            self.plugin.rootDir = os.path.abspath(self.dirEntry.get_text())
            self.plugin.versions = self.versionsEntry.get_text().replace(" ", "").split(",")
        ActionConfirmationDialog.respond(self, button, saidOK, *args)
