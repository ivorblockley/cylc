#!/usr/bin/env python

#C: THIS FILE IS PART OF THE CYLC SUITE ENGINE.
#C: Copyright (C) 2008-2013 Hilary Oliver, NIWA
#C:
#C: This program is free software: you can redistribute it and/or modify
#C: it under the terms of the GNU General Public License as published by
#C: the Free Software Foundation, either version 3 of the License, or
#C: (at your option) any later version.
#C:
#C: This program is distributed in the hope that it will be useful,
#C: but WITHOUT ANY WARRANTY; without even the implied warranty of
#C: MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#C: GNU General Public License for more details.
#C:
#C: You should have received a copy of the GNU General Public License
#C: along with this program.  If not, see <http://www.gnu.org/licenses/>.

import gobject
#import pygtk
#pygtk.require('2.0')
import gtk
import subprocess
import time, os, re, sys
import threading
from cylc.cycle_time import ct, CycleTimeError
from cylc.config import config, SuiteConfigError
from cylc.version import cylc_version
from cylc.suite_logging import suite_log
from cylc.suite_logging import suite_log
from util import EntryTempText

try:
    from cylc import cylc_pyro_client
except BaseException, x: # this catches SystemExit
    PyroInstalled = False
    print >> sys.stderr, "WARNING: Pyro is not installed."
else:
    PyroInstalled = True
    from cylc.port_scan import scan

from cylc.registration import localdb, RegistrationError
from cylc.regpath import RegPath
from warning_dialog import warning_dialog, info_dialog, question_dialog
from util import get_icon, get_image_dir, get_logo
import helpwindow
from gcapture import gcapture, gcapture_tmpfile
from graph import graph_suite_popup
from cylc.mkdir_p import mkdir_p
from cylc_logviewer import cylc_logviewer
from cylc.passphrase import passphrase

debug = False

class db_updater(threading.Thread):
    count = 0
    def __init__(self, regd_treestore, db, filtr=None, pyro_timeout=None ):
        self.__class__.count += 1
        self.me = self.__class__.count
        self.filtr = filtr
        self.db = db
        self.quit = False
        self.reload = False
        if pyro_timeout:
            self.pyro_timeout = float(pyro_timeout)
        else:
            self.pyro_timeout = None

        self.regd_treestore = regd_treestore
        super(db_updater, self).__init__()

        self.running_choices = []
        self.newtree = {}

        self.db.load_from_file()

        self.regd_choices = []
        self.regd_choices = self.db.get_list(filtr)

        # not needed:
        # self.build_treestore( self.newtree )
        self.construct_newtree()
        self.update()

    def construct_newtree( self ):
        # construct self.newtree[one][two]...[nnn] = [state, descr, dir ]
        self.running_choices_changed()
        ports = {}
        for suite in self.running_choices:
            reg, port = suite
            ports[ reg ] = port

        self.newtree = {}
        for reg in self.regd_choices:
            suite, suite_dir, descr = reg
            suite_dir = re.sub( '^' + os.environ['HOME'], '~', suite_dir )
            if suite in ports:
                state = str(ports[suite])
            else:
                state = '-'
            nest2 = self.newtree
            regp = suite.split(RegPath.delimiter)
            for key in regp[:-1]:
                if key not in nest2:
                    nest2[key] = {}
                nest2 = nest2[key]
            nest2[regp[-1]] = [ state, descr, suite_dir ]

    def build_treestore( self, data, piter=None ):
        items = data.keys()
        items.sort()
        for item in items:
            value = data[item]
            if isinstance( value, dict ):
                # final three items are colours
                iter = self.regd_treestore.append(piter, [item, None, None, None, None, None, None ] )
                self.build_treestore(value, iter)
            else:
                state, descr, dir = value
                iter = self.regd_treestore.append(piter, [item, state, descr, dir, None, None, None ] )

    def update( self ):
        #print "Updating list of available suites"
        self.construct_newtree()
        if self.reload:
            self.regd_treestore.clear()
            self.build_treestore( self.newtree )
            self.reload = False
        else:
            self.update_treestore( self.newtree, self.regd_treestore.get_iter_first() )

    def update_treestore( self, new, iter ):
        # iter is None for an empty treestore (no suites registered)
        ts = self.regd_treestore
        if iter:
            opath = ts.get_path(iter)
            # get parent iter before pruning in case we prune last item at this level
            piter = ts.iter_parent(iter)
        else:
            opath = None
            piter = None

        def my_get_iter( item ):
            # find the TreeIter pointing at item at this level
            if not opath:
                return None
            iter = ts.get_iter(opath)
            while iter:
                val, = ts.get( iter, 0 ) 
                if val == item:
                    return iter
                iter = ts.iter_next( iter )
            return None

        # new items at this level
        new_items = new.keys()
        old_items = []
        prune = []

        while iter:
            # iterate through old items at this level
            item, state, descr, dir = ts.get( iter, 0,1,2,3 )
            if item not in new_items:
                # old item is not in new - prune it
                res = ts.remove( iter )
                if not res: # Nec?
                    iter = None
            else:
                # old item is in new - update it in case it changed
                old_items.append(item)
                # update old items that do appear in new
                chiter = ts.iter_children(iter)
                if not isinstance( new[item], dict ):
                    # new item is not a group - update title etc.
                    state, descr, dir = new[item]
                    sc = self.statecol(state)
                    ni = new[item]
                    ts.set( iter, 0, item, 1, ni[0], 2, ni[1], 3, ni[2], 4, sc[0], 5, sc[1], 6, sc[2] )
                    if chiter:
                        # old item was a group - kill its children
                        while chiter:
                            res = ts.remove( chiter )
                            if not res:
                                chiter = None
                else:
                    # new item is a group
                    if not chiter:
                        # old item was not a group
                        ts.set( iter, 0, item, 1, None, 2, None, 3, None, 4, None, 5, None, 6, None )
                        self.build_treestore( new[item], iter )

                # continue
                iter = ts.iter_next( iter )

        # return to original iter
        if opath:
            try:
                iter = ts.get_iter(opath)
            except ValueError:
                # removed the item pointed to
                # TO DO: NEED TO WORRY ABOUT OTHERS AT THIS LEVEL?
                iter = None
        else:
            iter = None

        # add new items at this level
        for item in new_items:
            if item not in old_items:
                # new data wasn't in old - add it
                if isinstance( new[item], dict ):
                    xiter = ts.append(piter, [item] + [None, None, None, None, None, None] )
                    self.build_treestore( new[item], xiter )
                else:
                    state, descr, dir = new[item]
                    yiter = ts.append(piter, [item] + new[item] + list( self.statecol(state)))
            else:
                # new data was already in old
                if isinstance( new[item], dict ):
                    # check lower levels
                    niter = my_get_iter( item )
                    if niter:
                        chiter = ts.iter_children(niter)
                        if chiter:
                            self.update_treestore( new[item], chiter )

    def run( self ):
        global debug
        if debug:
            print '* thread', self.me, 'starting'
        while not self.quit:
            if self.running_choices_changed() or self.regd_choices_changed() or self.reload:
                gobject.idle_add( self.update )
            time.sleep(1)
        else:
            if debug:
                print '* thread', self.me, 'quitting'
            self.__class__.count -= 1
    
    def running_choices_changed( self ):
        if not PyroInstalled:
            return
        # (name, port)
        suites = scan( pyro_timeout=self.pyro_timeout, silent=True )
        if suites != self.running_choices:
            self.running_choices = suites
            return True
        else:
            return False

    def regd_choices_changed( self ):
        if not self.db.changed_on_disk():
            return False
        self.db.load_from_file()
        regs = self.db.get_list(self.filtr)
        if regs != self.regd_choices:
            self.regd_choices = regs
            return True
        else:
            return False

    def statecol( self, state ):
        grnbg = '#19ae0a'
        grnfg = '#030'
        #red = '#ff1a45'
        red = '#845'
        white = '#fff'
        black='#000'
        hilight = '#faf'
        hilight2 = '#f98e3a'
        if state == '-':
            #return (black, None, hilight)
            return (None, None, None)
        else:
            #return (grnfg, grnbg, hilight2 )
            return (grnfg, grnbg, grnbg )

    def search_level( self, model, iter, func, data ):
        while iter:
            if func( model, iter, data):
                return iter
            iter = model.iter_next(iter)
        return None

    def search_treemodel( self, model, iter, func, data ):
        while iter:
            if func( model, iter, data):
                return iter
            result = self.search_treemodel( model, model.iter_children(iter), func, data)
            if result:
                return result
            iter = model.iter_next(iter)
        return None

    def match_func( self, model, iter, data ):
        column, key = data
        value = model.get_value( iter, column )
        return value == key

class MainApp(object):
    def __init__(self, parent, db, db_owner, tmpdir, pyro_timeout ):

        self.db = db
        self.db_owner = db_owner
        if pyro_timeout:
            self.pyro_timeout = float(pyro_timeout)
        else:
            self.pyro_timeout = None

        self.regname = None

        self.updater = None
        self.tmpdir = tmpdir
        self.gcapture_windows = []

        gobject.threads_init()

        self.imagedir = get_image_dir()

        #self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window = gtk.Dialog( "Choose a suite", parent, gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OK, gtk.RESPONSE_OK))
        #self.window.set_modal(True)
        self.window.set_title("Registered Suites " + db )
        self.window.set_size_request(750, 400)
        self.window.set_icon(get_icon())
        #self.window.set_border_width( 5 )
        self.window.connect("delete_event", self.delete_all_event)

        sw = gtk.ScrolledWindow()
        sw.set_policy( gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC )

        self.regd_treeview = gtk.TreeView()
        self.regd_treestore = gtk.TreeStore( str, str, str, str, str, str, str )
        self.regd_treeview.set_model(self.regd_treestore)
        self.regd_treeview.set_rules_hint(True)
        # search column zero (Ctrl-F)
        self.regd_treeview.connect( 'key_press_event', self.on_suite_select )
        self.regd_treeview.connect( 'button_press_event', self.on_suite_select )
        self.regd_treeview.set_search_column(0)

        #exit_item = gtk.MenuItem( 'E_xit' )
        #exit_item.connect( 'activate', self.delete_all_event, None )
        #file_menu.append( exit_item )

        #self.menu_bar = gtk.MenuBar()
        #self.menu_bar.append( file_menu_root )

        # Start updating the liststore now, as we need values in it
        # immediately below (it may be possible to delay this till the
        # end of __init___() but it doesn't really matter.
        if self.db:
            self.dbopt = '--db='+self.db
        else:
            self.dbopt = ''

        regd_ts = self.regd_treeview.get_selection()
        regd_ts.set_mode( gtk.SELECTION_SINGLE )

        cr = gtk.CellRendererText()
        #cr.set_property( 'cell-background', '#def' )
        tvc = gtk.TreeViewColumn( 'Suite', cr, text=0, foreground=4, background=5 )
        tvc.set_resizable(True)
        tvc.set_sort_column_id(0)
        self.regd_treeview.append_column( tvc )

        cr = gtk.CellRendererText()
        tvc = gtk.TreeViewColumn( 'Port', cr, text=1, foreground=4, background=5 )
        tvc.set_resizable(True)
        # not sure how this sorting works
        #tvc.set_sort_column_id(1)
        self.regd_treeview.append_column( tvc ) 

        cr = gtk.CellRendererText()
        #cr.set_property( 'cell-background', '#def' )
        tvc = gtk.TreeViewColumn( 'Title', cr, markup=2, foreground=4, background=6 )
        tvc.set_resizable(True)
        #vc.set_sort_column_id(2)
        self.regd_treeview.append_column( tvc )

        cr = gtk.CellRendererText()
        tvc = gtk.TreeViewColumn( 'Location', cr, text=3, foreground=4, background=5 )
        tvc.set_resizable(True)
        #vc.set_sort_column_id(3)
        self.regd_treeview.append_column( tvc )

        vbox = self.window.vbox

        sw.add( self.regd_treeview )

        #vbox.pack_start( self.menu_bar, False )

        vbox.pack_start( sw, True )

        #eb = gtk.EventBox()
        #eb.add( gtk.Label( "left-click to select, right-click to view" ) )
        #eb.modify_bg( gtk.STATE_NORMAL, gtk.gdk.color_parse( '#8be' ) ) 
        #vbox.pack_start( eb, False )

        self.selected_label = gtk.Label( 'SELECTED: (none)' )

        filter_entry = EntryTempText()
        filter_entry.set_width_chars( 7 )  # Reduce width in toolbar
        filter_entry.connect( "activate", self.filter )
        filter_entry.set_temp_text( "filter" )
        filter_toolitem = gtk.ToolItem()
        filter_toolitem.add(filter_entry)
        tooltip = gtk.Tooltips()
        tooltip.enable()
        tooltip.set_tip(filter_toolitem, "Filter suites \n(enter a sub-string or regex)")

        expand_button = gtk.ToolButton()
        image = gtk.image_new_from_stock( gtk.STOCK_ADD, gtk.ICON_SIZE_SMALL_TOOLBAR )
        expand_button.set_icon_widget( image )
        expand_button.connect( 'clicked', lambda x: self.regd_treeview.expand_all() )

        collapse_button = gtk.ToolButton()
        image = gtk.image_new_from_stock( gtk.STOCK_REMOVE, gtk.ICON_SIZE_SMALL_TOOLBAR )
        collapse_button.set_icon_widget( image )        
        collapse_button.connect( 'clicked', lambda x: self.regd_treeview.collapse_all() )

        hbox = gtk.HBox()
        hbox.pack_start( self.selected_label, False )

        hbox.pack_start( gtk.HBox(), True )

        hbox.pack_start( expand_button, False )
        hbox.pack_start( collapse_button, False )

        hbox.pack_start (filter_toolitem, False)
 
        vbox.pack_start( hbox, False )

        self.window.show_all()

        self.start_updater()

    def start_updater(self, filtr=None ):
        db = localdb(self.db)
        #self.db_button.set_label( "_Local/Central DB" )
        if self.updater:
            self.updater.quit = True # does this take effect?
        self.updater = db_updater( self.regd_treestore, db, filtr, self.pyro_timeout )
        self.updater.start()

    # TODO: a button to do this?
    #def reload( self, w ):
    #    # tell updated to reconstruct the treeview from scratch
    #    self.updater.reload = True

    def filter(self, filtr_e ):
        if filtr_e == "":
            # reset
            self.start_updater()
            return
        filtr = filtr_e.get_text()
        try:
            re.compile( filtr )
        except:
            warning_dialog( "Bad Regular Expression: " + filtr, self.window ).warn()
            filtr_e.set_text("")
            self.start_updater()
            return
        self.start_updater( filtr )

    def delete_all_event( self, w, e ):
        self.updater.quit = True
        # call quit on any remaining gcapture windows, which contain
        # tailer threads that need to be stopped). Currently we maintain
        # a list of all gcapture windows opened
        # since start-up, hence the use of 'quit_already' to
        # avoid calling window.destroy() on gcapture windows that have
        # already been destroyed by the user closing them (although
        # a second call to destroy() may be safe anyway?)...
        for gwindow in self.gcapture_windows:
            if not gwindow.quit_already:
                gwindow.quit( None, None )

    def on_suite_select( self, treeview, event ):
        # popup menu on right click or 'Return' key only
        do_menu = True
        try:
            event.button
        except AttributeError:
            # not called by button click
            try:
                event.keyval
            except AttributeError:
                # not called by key press
                pass
            else:
                # called by key press
                keyname = gtk.gdk.keyval_name(event.keyval)
                if keyname != 'Return':
                    return False
                path, focus_col = treeview.get_cursor()
                if not path:
                    # no selection (prob treeview heading selected)
                    return False
                if not treeview.row_expanded(path):
                    # row not expanded or not expandable
                    iter = self.regd_treestore.get_iter(path)
                    if self.regd_treestore.iter_children(iter):
                        # has children so is expandable
                        treeview.expand_row(path, False )
                        return False
        else:
            # called by button click

            if event.button != 1:
                return False

            # the following sets selection to the position at which the
            # right click was done (otherwise selection lags behind the
            # right click):
            x = int( event.x )
            y = int( event.y )
            time = event.time
            pth = treeview.get_path_at_pos(x,y)
            if pth is None:
                return False
            treeview.grab_focus()
            path, col, cellx, celly = pth
            treeview.set_cursor( path, col, 0 )
 
        selection = treeview.get_selection()

        model, iter = selection.get_selected()

        item, state, descr, suite_dir = model.get( iter, 0,1,2,3 )
        if not suite_dir:
            group_clicked = True
        else:
            group_clicked = False
 
        def get_reg( item, iter ):
            reg = item
            if iter:
                par = model.iter_parent( iter )
                if par:
                    val, = model.get(par, 0)
                    reg = get_reg( val, par ) + RegPath.delimiter + reg
            return reg

        reg = get_reg( item, iter )
        if not group_clicked:
            self.regname = reg
            self.selected_label.set_text( 'SELECTED: ' + reg )
        else:
            self.regname = None
            self.selected_label.set_text( 'SELECTED: (none)' )

        #if not do_menu:
        #return True
        return False

        menu = gtk.Menu()

        menu_root = gtk.MenuItem( 'foo' )
        menu_root.set_submenu( menu )

        if group_clicked:
            group = reg
            # MENU OPTIONS FOR GROUPS
            copy_item = gtk.MenuItem( 'C_opy' )
            menu.append( copy_item )
            copy_item.connect( 'activate', self.copy_popup, group, True )

            reregister_item = gtk.MenuItem( '_Reregister' )
            menu.append( reregister_item )
            reregister_item.connect( 'activate', self.reregister_popup, group, True )

            del_item = gtk.MenuItem( '_Unregister' )
            menu.append( del_item )
            del_item.connect( 'activate', self.unregister_popup, group, True )

        else:
            # MENU OPTIONS FOR SUITES
            infomenu_item = gtk.MenuItem( '_Information' )
            infomenu = gtk.Menu()
            infomenu_item.set_submenu(infomenu)
 
            descr_item = gtk.MenuItem( '_Description' )
            infomenu.append( descr_item )
            descr_item.connect( 'activate', self.describe_suite, reg )

            listitem = gtk.MenuItem( '_List' )
            infomenu.append( listitem )
            listmenu = gtk.Menu()
            listitem.set_submenu(listmenu)
 
            flat_item = gtk.MenuItem( '_Tasks' )
            listmenu.append( flat_item )
            flat_item.connect( 'activate', self.list_suite, reg )

            tree_item = gtk.MenuItem( '_Namespaces' )
            listmenu.append( tree_item )
            tree_item.connect( 'activate', self.list_suite, reg, '-t' )

            igraph_item = gtk.MenuItem( '_Graph' )
            infomenu.append( igraph_item )
            igraphmenu = gtk.Menu()
            igraph_item.set_submenu(igraphmenu)

            igtree_item = gtk.MenuItem( '_Dependencies' )
            igraphmenu.append( igtree_item )
            igtree_item.connect( 'activate', self.graph_suite_popup_driver, reg )

            igns_item = gtk.MenuItem( '_Namespaces' )
            igraphmenu.append( igns_item )
            igns_item.connect( 'activate', self.nsgraph_suite, reg )

            jobs_item = gtk.MenuItem( 'Generate A _Job Script')
            infomenu.append( jobs_item )
            jobs_item.connect( 'activate', self.jobscript_popup, reg )
 
            if state != '-':
                # suite is running
                dump_item = gtk.MenuItem( 'D_ump Suite State' )
                infomenu.append( dump_item )
                dump_item.connect( 'activate', self.dump_suite, reg )
   
            prepmenu_item = gtk.MenuItem( '_Preparation' )
            prepmenu = gtk.Menu()
            prepmenu_item.set_submenu(prepmenu)
    
            pdescr_item = gtk.MenuItem( '_Description' )
            prepmenu.append( pdescr_item )
            pdescr_item.connect( 'activate', self.describe_suite, reg )

            edit_item = gtk.MenuItem( '_Edit' )
            prepmenu.append( edit_item )
            editmenu = gtk.Menu()
            edit_item.set_submenu(editmenu)

            raw_item = gtk.MenuItem( '_Raw' )
            editmenu.append( raw_item )
            raw_item.connect( 'activate', self.edit_suite, reg, False )
    
            inl_item = gtk.MenuItem( '_Inlined' )
            editmenu.append( inl_item )
            inl_item.connect( 'activate', self.edit_suite, reg, True )
 
            view_item = gtk.MenuItem( '_View' )
            prepmenu.append( view_item )
            viewmenu = gtk.Menu()
            view_item.set_submenu(viewmenu)

            rw_item = gtk.MenuItem( '_Raw' )
            viewmenu.append( rw_item )
            rw_item.connect( 'activate', self.view_suite, reg, 'raw' )
 
            viewi_item = gtk.MenuItem( '_Inlined' )
            viewmenu.append( viewi_item )
            viewi_item.connect( 'activate', self.view_suite, reg, 'inlined' )
 
            viewp_item = gtk.MenuItem( '_Processed' )
            viewmenu.append( viewp_item )
            viewp_item.connect( 'activate', self.view_suite, reg, 'processed' )

            plistitem = gtk.MenuItem( '_List' )
            prepmenu.append( plistitem )
            plistmenu = gtk.Menu()
            plistitem.set_submenu(plistmenu)
 
            pflat_item = gtk.MenuItem( '_Tasks' )
            plistmenu.append( pflat_item )
            pflat_item.connect( 'activate', self.list_suite, reg )

            ptree_item = gtk.MenuItem( '_Namespaces' )
            plistmenu.append( ptree_item )
            ptree_item.connect( 'activate', self.list_suite, reg, '-t' )
 
            graph_item = gtk.MenuItem( '_Graph' )
            prepmenu.append( graph_item )
            graphmenu = gtk.Menu()
            graph_item.set_submenu(graphmenu)

            gtree_item = gtk.MenuItem( '_Dependencies' )
            graphmenu.append( gtree_item )
            gtree_item.connect( 'activate', self.graph_suite_popup_driver, reg )

            gns_item = gtk.MenuItem( '_Namespaces' )
            graphmenu.append( gns_item )
            gns_item.connect( 'activate', self.nsgraph_suite, reg )

            search_item = gtk.MenuItem( '_Search' )
            prepmenu.append( search_item )
            search_item.connect( 'activate', self.search_suite_popup, reg )

            val_item = gtk.MenuItem( '_Validate' )
            prepmenu.append( val_item )
            val_item.connect( 'activate', self.validate_suite, reg )
    
            dbmenu_item = gtk.MenuItem( '_Database' )
            dbmenu = gtk.Menu()
            dbmenu_item.set_submenu(dbmenu)
    
            copy_item = gtk.MenuItem( '_Copy' )
            dbmenu.append( copy_item )
            copy_item.connect( 'activate', self.copy_popup, reg )

            alias_item = gtk.MenuItem( '_Alias' )
            dbmenu.append( alias_item )
            alias_item.connect( 'activate', self.alias_popup, reg )
    
            compare_item = gtk.MenuItem( 'C_ompare' )
            dbmenu.append( compare_item )
            compare_item.connect( 'activate', self.compare_popup, reg )
 
            reregister_item = gtk.MenuItem( '_Reregister' )
            dbmenu.append( reregister_item )
            reregister_item.connect( 'activate', self.reregister_popup, reg )
    
            del_item = gtk.MenuItem( '_Unregister' )
            dbmenu.append( del_item )
            del_item.connect( 'activate', self.unregister_popup, reg )

            menu.append( prepmenu_item )
            menu.append( infomenu_item )
            menu.append( dbmenu_item )

        menu.show_all()
        # button only:
        #menu.popup( None, None, None, event.button, event.time )
        # this seems to work with keypress and button:
        menu.popup( None, None, None, 0, event.time )

        # TO DO: POPUP MENU MUST BE DESTROY()ED AFTER EVERY USE AS
        # POPPING DOWN DOES NOT DO THIS (=> MEMORY LEAK?)
        return False


    def alias_popup( self, w, reg ):
        window = gtk.Window()
        window.set_border_width(5)
        window.set_title( "Alias A Suite")
        window.set_transient_for( self.window )
        window.set_type_hint( gtk.gdk.WINDOW_TYPE_HINT_DIALOG )

        vbox = gtk.VBox()
        label = gtk.Label( "SUITE: " + reg )
        vbox.pack_start( label )

        box = gtk.HBox()
        label = gtk.Label( 'ALIAS:' )
        box.pack_start( label, True )
        alias_entry = gtk.Entry()
        alias_entry.set_text( reg )
        box.pack_start (alias_entry, True)
        vbox.pack_start(box)

        cancel_button = gtk.Button( "_Cancel" )
        cancel_button.connect("clicked", lambda x: window.destroy() )

        ok_button = gtk.Button( "_Alias" )
        ok_button.connect("clicked", self.alias_suite, window, reg, alias_entry )

        help_button = gtk.Button( "_Help" )
        help_button.connect("clicked", self.command_help, 'db', 'alias' )

        hbox = gtk.HBox()
        hbox.pack_start( ok_button, False )
        hbox.pack_end( cancel_button, False )
        hbox.pack_end( help_button, False )
        vbox.pack_start( hbox )

        window.add( vbox )
        window.show_all()

    def alias_suite( self, b, w, reg, alias_entry ):
        command = "cylc alias --notify-completion " + self.dbopt + " " + reg + " " + alias_entry.get_text()
        foo = gcapture_tmpfile( command, self.tmpdir, 600 )
        self.gcapture_windows.append(foo)
        foo.run()
        w.destroy()

    def unregister_popup( self, w, reg, is_group=False ):
        window = gtk.Window()
        window.set_border_width(5)
        window.set_title( "Unregister Suite(s)")
        window.set_transient_for( self.window )
        window.set_type_hint( gtk.gdk.WINDOW_TYPE_HINT_DIALOG )

        vbox = gtk.VBox()

        cancel_button = gtk.Button( "_Cancel" )
        cancel_button.connect("clicked", lambda x: window.destroy() )

        oblit_cb = gtk.CheckButton( "_Delete suite definition directories" )
        oblit_cb.set_active(False)

        ok_button = gtk.Button( "_Unregister" )
        ok_button.connect("clicked", self.unregister_suites, window, reg, oblit_cb, is_group )

        help_button = gtk.Button( "_Help" )
        help_button.connect("clicked", self.command_help, 'db', 'unregister' )

        label = gtk.Label( "SUITE: " + reg )
        vbox.pack_start( label )
        vbox.pack_start( oblit_cb )

        hbox = gtk.HBox()
        hbox.pack_start( ok_button, False )
        hbox.pack_end( cancel_button, False )
        hbox.pack_end( help_button, False )
        vbox.pack_start( hbox )

        window.add( vbox )
        window.show_all()

    def unregister_suites( self, b, w, reg, oblit_cb, is_group ):
        options = ''
        if oblit_cb.get_active():
            res = question_dialog( "!DANGER! !DANGER! !DANGER! !DANGER! !DANGER! !DANGER!\n"
                    "?Do you REALLY want to delete the associated suite definitions?",
                    self.window ).ask()
            if res == gtk.RESPONSE_YES:
                options = '--delete '
            else:
                return False
 
        if is_group:
            reg = '^' + reg + '\..*$'
        else:
            reg = '^' + reg + '$'

        command = "cylc unregister " + self.dbopt + " --notify-completion --force " + options + reg
        foo = gcapture_tmpfile( command, self.tmpdir, 600 )
        self.gcapture_windows.append(foo)
        foo.run()
        w.destroy()

    def browse( self, b, option='' ):
        command = 'cylc documentation ' + option
        foo = gcapture_tmpfile( command, self.tmpdir, 700 )
        self.gcapture_windows.append(foo)
        foo.run()

    def toggle_entry_sensitivity( self, w, entry ):
        if entry.get_property( 'sensitive' ) == 0:
            entry.set_sensitive( True )
        else:
            entry.set_sensitive( False )

    def reregister_popup( self, w, reg, is_group=False ):
        window = gtk.Window()
        window.set_border_width(5)
        window.set_title( "Reregister Suite(s)" )
        window.set_transient_for( self.window )
        window.set_type_hint( gtk.gdk.WINDOW_TYPE_HINT_DIALOG )

        vbox = gtk.VBox()

        label = gtk.Label("SOURCE: " + reg )
        vbox.pack_start( label )
 
        label = gtk.Label("TARGET: " )
        name_entry = gtk.Entry()
        name_entry.set_text( reg )
        hbox = gtk.HBox()
        hbox.pack_start( label )
        hbox.pack_start(name_entry, True) 
        vbox.pack_start( hbox )

        cancel_button = gtk.Button( "_Cancel" )
        cancel_button.connect("clicked", lambda x: window.destroy() )

        ok_button = gtk.Button( "_Reregister" )
        ok_button.connect("clicked", self.reregister_suites, window, reg, name_entry, is_group )

        help_button = gtk.Button( "_Help" )
        help_button.connect("clicked", self.command_help, 'db', 'reregister' )

        hbox = gtk.HBox()
        hbox.pack_start( ok_button, False )
        hbox.pack_end( cancel_button, False )
        hbox.pack_end( help_button, False )
        vbox.pack_start( hbox )

        window.add( vbox )
        window.show_all()

    def reregister_suites( self, b, w, reg, n_e, is_group ):
        newreg = n_e.get_text()
        command = "cylc reregister " + self.dbopt + " --notify-completion " + reg + ' ' + newreg
        foo = gcapture_tmpfile( command, self.tmpdir, 600 )
        self.gcapture_windows.append(foo)
        foo.run()
        w.destroy()

    def compare_popup( self, w, reg ):
        window = gtk.Window()
        window.set_border_width(5)
        window.set_title( "Compare")
        window.set_transient_for( self.window )
        window.set_type_hint( gtk.gdk.WINDOW_TYPE_HINT_DIALOG )

        vbox = gtk.VBox()
        label = gtk.Label("SUITE1: " + reg)
        vbox.pack_start(label)

        label = gtk.Label("SUITE2:" )
        name_entry = gtk.Entry()
        name_entry.set_text( reg )
        hbox = gtk.HBox()
        hbox.pack_start( label )
        hbox.pack_start(name_entry, True) 
        vbox.pack_start( hbox )

        nested_cb = gtk.CheckButton( "Nested section headings" )
        nested_cb.set_active(False)
        vbox.pack_start (nested_cb, True)

        cancel_button = gtk.Button( "_Cancel" )
        cancel_button.connect("clicked", lambda x: window.destroy() )

        ok_button = gtk.Button( "Co_mpare" )
        ok_button.connect("clicked", self.compare_suites, window, reg, name_entry, nested_cb )

        help_button = gtk.Button( "_Help" )
        help_button.connect("clicked", self.command_help, 'prep', 'compare'  )

        hbox = gtk.HBox()
        hbox.pack_start( ok_button, False )
        hbox.pack_end( cancel_button, False )
        hbox.pack_end( help_button, False )
        vbox.pack_start( hbox )

        window.add( vbox )
        window.show_all()

    def copy_popup( self, w, reg, is_group=False ):

        window = gtk.Window()
        window.set_border_width(5)
        window.set_title( "Copy Suite(s)")
        window.set_transient_for( self.window )
        window.set_type_hint( gtk.gdk.WINDOW_TYPE_HINT_DIALOG )

        vbox = gtk.VBox()

        label = gtk.Label("SOURCE: " + reg )
        vbox.pack_start( label )

        label = gtk.Label("TARGET" )
        name_entry = gtk.Entry()
        name_entry.set_text( reg )
        hbox = gtk.HBox()
        hbox.pack_start( label )
        hbox.pack_start(name_entry, True) 
        vbox.pack_start( hbox )

        box = gtk.HBox()
        label = gtk.Label( 'TOPDIR' )
        box.pack_start( label, True )
        dir_entry = gtk.Entry()
        box.pack_start (dir_entry, True)
        vbox.pack_start(box)

        cancel_button = gtk.Button( "_Cancel" )
        cancel_button.connect("clicked", lambda x: window.destroy() )

        ok_button = gtk.Button( "Co_py" )
        ok_button.connect("clicked", self.copy_suites, window, reg, name_entry, dir_entry, is_group )

        help_button = gtk.Button( "_Help" )
        help_button.connect("clicked", self.command_help, 'db', 'copy')

        hbox = gtk.HBox()
        hbox.pack_start( ok_button, False )
        hbox.pack_end( cancel_button, False )
        hbox.pack_end( help_button, False )
        vbox.pack_start( hbox )

        window.add( vbox )
        window.show_all()

    def compare_suites( self, b, w, reg, name_entry, nested_cb ):
        name  = name_entry.get_text()
        chk = [ name ]
        opts = ''
        if nested_cb.get_active():
            opts = ' -n '
        if not self.check_entries( chk ):
            return False
        command = "cylc diff " + self.dbopt + " --notify-completion " + opts + reg + ' ' + name
        foo = gcapture_tmpfile( command, self.tmpdir, 800 )
        self.gcapture_windows.append(foo)
        foo.run()
        w.destroy()
 
    def copy_suites( self, b, w, reg, name_entry, dir_entry, is_group ):
        name  = name_entry.get_text()
        sdir  = dir_entry.get_text()
        chk = [ name, sdir ]
        if not self.check_entries( chk ):
            return False
        #if is_group:
        #    reg = '^' + reg + '\..*$'
        #else:
        #    reg = '^' + reg + '$'
        command = "cylc copy --notify-completion " + self.dbopt + ' ' + reg + ' ' + name + ' ' + sdir
        foo = gcapture_tmpfile( command, self.tmpdir, 600 )
        self.gcapture_windows.append(foo)
        foo.run()
        w.destroy()
 
    def search_suite_popup( self, w, reg ):
        window = gtk.Window()
        window.set_border_width(5)
        window.set_title( "Suite Search" )
        window.set_transient_for( self.window )
        window.set_type_hint( gtk.gdk.WINDOW_TYPE_HINT_DIALOG )

        vbox = gtk.VBox()

        label = gtk.Label("SUITE: " + reg )
        vbox.pack_start(label)

        label = gtk.Label("PATTERN" )
        pattern_entry = gtk.Entry()
        hbox = gtk.HBox()
        hbox.pack_start( label )
        hbox.pack_start(pattern_entry, True) 
        vbox.pack_start( hbox )

        yesbin_cb = gtk.CheckButton( "Also search suite bin directory" )
        yesbin_cb.set_active(True)
        vbox.pack_start (yesbin_cb, True)

        cancel_button = gtk.Button( "_Cancel" )
        cancel_button.connect("clicked", lambda x: window.destroy() )

        ok_button = gtk.Button( "_Search" )
        ok_button.connect("clicked", self.search_suite, reg, yesbin_cb, pattern_entry )

        help_button = gtk.Button( "_Help" )
        help_button.connect("clicked", self.command_help, 'prep', 'search' )

        hbox = gtk.HBox()
        hbox.pack_start( ok_button, False )
        hbox.pack_end( cancel_button, False )
        hbox.pack_end( help_button, False )
        vbox.pack_start( hbox )

        window.add( vbox )
        window.show_all()

    def search_suite( self, w, reg, yesbin_cb, pattern_entry ):
        pattern = pattern_entry.get_text()
        options = ''
        if not yesbin_cb.get_active():
            options += ' -x '
        command = "cylc search " + self.dbopt + " --notify-completion " + options + ' ' + reg + ' ' + pattern 
        foo = gcapture_tmpfile( command, self.tmpdir, width=600, height=500 )
        self.gcapture_windows.append(foo)
        foo.run()

    def graph_suite_popup_driver( self, w, reg ):
        # don't bother extracting [visualization] start and stop cycles
        # to insert in the popup. The suite has to be parsed again for
        # the graph and doing that twice is bad for very large suites. 
        # (We could provide a load button like the suite start popup does).
        template_opts = ""
        graph_suite_popup( reg, self.command_help, None, None, " " + self.dbopt,
                           self.gcapture_windows, self.tmpdir, template_opts, self.window )
        return False

    def view_suite( self, w, reg, method ):
        extra = ''
        if method == 'inlined':
            extra = ' -i'
        elif method == 'processed':
            extra = ' -j'

        command = "cylc view " + self.dbopt + " --notify-completion -g " + extra + ' ' + reg
        foo = gcapture_tmpfile( command, self.tmpdir )
        self.gcapture_windows.append(foo)
        foo.run()
        return False

    def edit_suite( self, w, reg, inlined ):
        extra = ''
        if inlined:
            extra = '-i '
        command = "cylc edit " + self.dbopt + " --notify-completion -g " + extra + ' ' + reg
        foo = gcapture_tmpfile( command, self.tmpdir )
        self.gcapture_windows.append(foo)
        foo.run()
        return False

    def validate_suite( self, w, name ):
        command = "cylc validate -v " + self.dbopt + " --notify-completion " + name 
        foo = gcapture_tmpfile( command, self.tmpdir, 700 )
        self.gcapture_windows.append(foo)
        foo.run()

    def dump_suite( self, w, name ):
        command = "cylc dump --notify-completion " + name
        foo = gcapture_tmpfile( command, self.tmpdir, 400, 400 )
        self.gcapture_windows.append(foo)
        foo.run()

    def jobscript_popup( self, w, reg ):
        window = gtk.Window()
        window.set_border_width(5)
        window.set_title( "Generate A Task Job Script")
        window.set_transient_for( self.window )
        window.set_type_hint( gtk.gdk.WINDOW_TYPE_HINT_DIALOG )

        vbox = gtk.VBox()
        label = gtk.Label("SUITE: " + reg )
        vbox.pack_start( label )

        label = gtk.Label("TASK ID: " )
        task_entry = gtk.Entry()
        hbox = gtk.HBox()
        hbox.pack_start( label, True )
        hbox.pack_start(task_entry, True) 
        vbox.pack_start( hbox )
 
        cancel_button = gtk.Button( "_Close" )
        cancel_button.connect("clicked", lambda x: window.destroy() )

        ok_button = gtk.Button( "_Generate" )
        ok_button.connect("clicked", self.jobscript, reg, task_entry )

        help_button = gtk.Button( "_Help" )
        help_button.connect("clicked", self.command_help, 'prep', 'jobscript' )

        hbox = gtk.HBox()
        hbox.pack_start( ok_button, False )
        hbox.pack_end( cancel_button, False )
        hbox.pack_end( help_button, False )
        vbox.pack_start( hbox )

        window.add( vbox )
        window.show_all()

    def jobscript( self, w, reg, task_entry ):
        command = "cylc jobscript " + self.dbopt + " " + reg + " " + task_entry.get_text()
        foo = gcapture_tmpfile( command, self.tmpdir, 800, 800 )
        self.gcapture_windows.append(foo)
        foo.run()

    def describe_suite( self, w, name ):
        command = """echo '> TITLE:'; cylc get-config """ + self.dbopt + " -i title " + name + """; echo
echo '> DESCRIPTION:'; cylc get-config """ + self.dbopt + " --notify-completion -i description " + name 
        foo = gcapture_tmpfile( command, self.tmpdir, 800, 400 )
        self.gcapture_windows.append(foo)
        foo.run()

    def list_suite( self, w, name, opt='' ):
        command = "cylc list " + self.dbopt + " " + opt + " --notify-completion " + name
        foo = gcapture_tmpfile( command, self.tmpdir, 600, 600 )
        self.gcapture_windows.append(foo)
        foo.run()

    def nsgraph_suite( self, w, name ):
        command = "cylc graph --namespaces " + self.dbopt + " --notify-completion " + name
        foo = gcapture_tmpfile( command, self.tmpdir )
        self.gcapture_windows.append(foo)
        foo.run()

    def close_log_window( self, w, e, window, clv ):
        window.destroy()
        clv.quit()

    def check_entries( self, entries ):
        # note this check retrieved entry values
        bad = False
        for entry in entries:
            if entry == '':
                bad = True
        if bad:
            warning_dialog( "Please complete all required text entry panels!",
                            self.window ).warn()
            return False
        else:
            return True
