"""StatusNotifierItem and DBusMenu; no desktop-specific library required."""
from gi.repository import Gio, GLib

ITEM='/StatusNotifierItem'
MENU='/MenuBar'
WATCHER='org.kde.StatusNotifierWatcher'
ITEM_XML="""<node><interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="WindowId" type="u" access="read"/><property name="IconName" type="s" access="read"/>
<property name="IconThemePath" type="s" access="read"/><property name="IconPixmap" type="a(iiay)" access="read"/>
<property name="OverlayIconName" type="s" access="read"/><property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
<property name="AttentionIconName" type="s" access="read"/><property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
<property name="AttentionMovieName" type="s" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/><property name="Menu" type="o" access="read"/>
<signal name="NewIcon"/><signal name="NewStatus"><arg type="s"/></signal>
</interface></node>"""
MENU_XML="""<node><interface name="com.canonical.dbusmenu">
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/><arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
<property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/><property name="Status" type="s" access="read"/><property name="IconThemePath" type="as" access="read"/>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
<signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
</interface></node>"""
V=GLib.Variant

class Tray:
    def __init__(self,app,icon):
        self.app=app
        self.icon=icon
        self.revision=1
        self.server_state="stopped"
        self.window_visible=bool(app.window and app.window.get_visible())
        self.available=False
        self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        self.item_info=Gio.DBusNodeInfo.new_for_xml(ITEM_XML)
        self.menu_info=Gio.DBusNodeInfo.new_for_xml(MENU_XML)
        self.ids=[
            self.bus.register_object(ITEM,self.item_info.interfaces[0],self.item_method,self.item_property,None),
            self.bus.register_object(MENU,self.menu_info.interfaces[0],self.menu_method,self.menu_property,None)]
        self.watch=Gio.bus_watch_name_on_connection(self.bus,WATCHER,Gio.BusNameWatcherFlags.NONE,self.appeared,self.vanished)
    def appeared(self,bus,name,owner):
        bus.call(WATCHER,'/StatusNotifierWatcher',WATCHER,'RegisterStatusNotifierItem',
                 V('(s)',(ITEM,)),None,Gio.DBusCallFlags.NONE,3000,None,self.registered)
    def vanished(self,bus,name):
        self.available=False
        self.app.tray_lost()
    def registered(self,bus,result):
        try:
            bus.call_finish(result)
            self.available=True
        except GLib.Error as e:
            self.available=False
            print('Tray registration:',e.message,flush=True)
    def item_property(self,bus,sender,path,interface,name):
        values={
            'Category':V('s','ApplicationStatus'),'Id':V('s','quantru'),'Title':V('s','Quantru'),
            'Status':V('s','Active'),'WindowId':V('u',0),'IconName':V('s',self.icon),
            'IconThemePath':V('s',''),'IconPixmap':V('a(iiay)',[]),
            'OverlayIconName':V('s',''),'OverlayIconPixmap':V('a(iiay)',[]),
            'AttentionIconName':V('s',''),'AttentionIconPixmap':V('a(iiay)',[]),
            'AttentionMovieName':V('s',''),'ToolTip':V('(sa(iiay)ss)',(self.icon,[],'Quantru','')),
            'ItemIsMenu':V('b',False),'Menu':V('o',MENU)}
        return values.get(name)
    def item_method(self,bus,sender,path,interface,method,args,inv):
        if method in ('Activate','SecondaryActivate'):GLib.idle_add(self.app.tray_open)
        inv.return_value(V('()',()))
    def props(self,item):
        if item==0:return {'children-display':V('s','submenu')}
        labels={1:'Hide Quantru' if self.window_visible else 'Show Quantru',2:{'running':'Stop server','stopped':'Start server','starting':'Starting server…','stopping':'Stopping server…'}[self.server_state],3:'Quit Quantru'}
        if item not in labels:return {}
        return {'label':V('s',labels[item]),'enabled':V('b',item!=2 or self.server_state in ('running','stopped')),'visible':V('b',True)}
    def layout(self,item,depth,names):
        props=self.props(item)
        if names:props={k:v for k,v in props.items() if k in names}
        children=[V('(ia{sv}av)',self.layout(i,0,names)) for i in (1,2,3)] if item==0 and depth!=0 else []
        return (item,props,children)
    def click(self,item,event):
        if event=='clicked':
            action={1:self.app.tray_toggle_window,2:self.app.tray_toggle_server,3:self.app.tray_quit}.get(item)
            if item==2 and self.server_state not in ("running","stopped"):return
            if action:GLib.idle_add(action)
    def menu_method(self,bus,sender,path,interface,method,args,inv):
        try:
            a=args.unpack()
            if method=='GetLayout':
                value=V('(u(ia{sv}av))',(self.revision,self.layout(*a)))
            elif method=='GetGroupProperties':
                ids,names=a
                value=V('(a(ia{sv}))',([(i,{k:v for k,v in self.props(i).items() if not names or k in names}) for i in (ids or [0,1,2,3]) if i in (0,1,2,3)],))
            elif method=='GetProperty':
                value=V('(v)',(self.props(a[0])[a[1]],))
            elif method=='Event':
                self.click(a[0],a[1]);value=V('()',())
            elif method=='EventGroup':
                for item,event,_,_ in a[0]:self.click(item,event)
                value=V('(ai)',([],))
            elif method=='AboutToShow':
                previous=self.revision
                self.app.refresh_tray_state()
                value=V('(b)',(previous!=self.revision,))
            elif method=='AboutToShowGroup':
                previous=self.revision
                self.app.refresh_tray_state()
                value=V('(aiai)',(a[0] if previous!=self.revision else [],[]))
            else:raise ValueError('Unknown menu method')
            inv.return_value(value)
        except Exception as e:inv.return_dbus_error('com.canonical.dbusmenu.Error',str(e))
    def menu_property(self,bus,sender,path,interface,name):
        return {'Version':V('u',3),'TextDirection':V('s','ltr'),'Status':V('s','normal'),'IconThemePath':V('as',[])}.get(name)
    def update_item(self,item):
        self.revision+=1
        self.bus.emit_signal(None,MENU,'com.canonical.dbusmenu','ItemsPropertiesUpdated',
                             V('(a(ia{sv})a(ias))',([(item,self.props(item))],[])))
        self.bus.emit_signal(None,MENU,'com.canonical.dbusmenu','LayoutUpdated',V('(ui)',(self.revision,0)))
    def set_window_visible(self,visible):
        if self.window_visible==visible:return
        self.window_visible=visible
        self.update_item(1)
    def set_server_state(self,state):
        if self.server_state==state:return
        self.server_state=state
        self.update_item(2)
    def set_running(self,running):
        self.set_server_state('running' if running else 'stopped')
    def close(self):
        Gio.bus_unwatch_name(self.watch)
        for ident in self.ids:self.bus.unregister_object(ident)
