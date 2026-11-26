#!/usr/bin/env python3
"""Quantru's native Linux window. The same local web application is embedded."""
import os
import hashlib
import pathlib
import subprocess
import sys
import urllib.request
import urllib.error
import json
import time
from tray import Tray

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('WebKit', '6.0')
gi.require_version('JavaScriptCore', '6.0')
from gi.repository import Gtk, Adw, WebKit, Gio, GLib, Gdk, JavaScriptCore as JSC

ROOT = pathlib.Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8765/'
APP_ID = 'io.github.quantru.App'

def backend_status():
    try:
        with urllib.request.urlopen(URL+'api/health', timeout=.5) as response:
            return json.load(response).get('status')
    except urllib.error.HTTPError as e:
        try:return json.load(e).get('status')
        except (ValueError,OSError):return None
    except (OSError,ValueError):return None

def web_available():
    try:
        with urllib.request.urlopen(URL+'__instance',timeout=.5) as response:
            expected=hashlib.sha256((str(ROOT)+':'+str(os.getuid())).encode()).hexdigest()
            return response.read().decode()==expected
    except OSError:return False

class Quantru(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.server=None
        self.window=None
        self.view=None
        self.poll_source=0
        self.start_time=0
        self.audio_allowed=False
        self.downloads=set()
        self.tray=None
        self.server_paused=False
        self.stopping=False
        self.hidden_hold=False

    def do_activate(self):
        if self.window is not None:
            self.tray_open()
            return
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        self.window=Adw.ApplicationWindow(application=self,title='Quantru')
        self.window.connect('close-request',self.close_window)
        self.window.set_icon_name(APP_ID)
        self.window.set_default_size(1000,650)
        self.window.set_size_request(360,420)
        layout=Gtk.Overlay()
        header=Gtk.WindowControls.new(Gtk.PackType.END)
        header.set_decoration_layout(':minimize,maximize,close')
        header.set_halign(Gtk.Align.END)
        header.set_valign(Gtk.Align.START)
        header.set_margin_top(8)
        header.set_margin_end(8)
        header.add_css_class('quantru-header')
        css=Gtk.CssProvider()
        css.load_from_data(b'.quantru-header { background: transparent; color: #eee; box-shadow: none; border: none; padding: 0; margin: 0; }')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.overlay=Adw.ToastOverlay()
        self.stack=Gtk.Stack()
        self.overlay.set_child(self.stack)
        layout.set_child(self.overlay)
        # Invisible native drag region, leaving the logo and window controls free.
        drag_area=Gtk.WindowHandle.new()
        drag_area.set_halign(Gtk.Align.FILL)
        drag_area.set_valign(Gtk.Align.START)
        drag_area.set_margin_start(60)
        drag_area.set_margin_end(124)
        drag_area.set_size_request(-1,24)
        drag_area.set_child(Gtk.Box())
        layout.add_overlay(drag_area)
        layout.set_measure_overlay(drag_area,False)
        layout.add_overlay(header)
        layout.set_measure_overlay(header,False)
        self.window.set_content(layout)
        self.waiting=Adw.StatusPage(title='Starting Quantru',description='Connecting to the local server…',icon_name='system-run-symbolic')
        self.retry=Gtk.Button(label='Retry',halign=Gtk.Align.CENTER)
        self.retry.add_css_class('suggested-action')
        self.retry.connect('clicked',lambda *_:self.start_backend())
        self.waiting.set_child(self.retry)
        self.stack.add_named(self.waiting,'waiting')
        data=pathlib.Path(os.environ.get('XDG_DATA_HOME',str(pathlib.Path.home()/'.local/share')))/'quantru/webkit'
        cache=pathlib.Path(os.environ.get('XDG_CACHE_HOME',str(pathlib.Path.home()/'.cache')))/'quantru/webkit'
        data.mkdir(parents=True,exist_ok=True,mode=0o700)
        cache.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.session=WebKit.NetworkSession.new(str(data),str(cache))
        self.session.connect('download-started',self.download_started)
        self.view=WebKit.WebView(network_session=self.session)
        # Keep the native app free of browser context menus.
        self.view.connect('context-menu', lambda *_: True)
        # WebKit can select the emoji face for ASCII whitespace and digits
        # even with a unicode-range. Use a text-first stack in the native view.
        native_css=WebKit.UserStyleSheet.new(
            'html,body,.chat-open,.chat-rename input {font-family: "Noto Sans", "DejaVu Sans", sans-serif, "Noto Color Emoji" !important; word-spacing: normal !important;} '
            '.markdown code {font-family: "DejaVu Sans Mono", monospace, "Noto Color Emoji" !important; word-spacing: normal !important;} '
            'html,body,main {background-color:#242424 !important;} '
            '.html-preview .preview-header {height:86px !important; padding-top:44px !important;} '
            'main:has(.message) .composer-dock {align-self:stretch; width:auto !important; background-color:#242424 !important;} '
            '* {scrollbar-color: auto !important; scrollbar-width: auto !important;} '
            '*::-webkit-scrollbar {width: 5px; height: 5px;} '
            '*::-webkit-scrollbar-track {background: transparent;} '
            '*::-webkit-scrollbar-thumb {background: #626262; border-radius: 999px;} '
            '*::-webkit-scrollbar-thumb:hover, *::-webkit-scrollbar-thumb:active {background: #858585 !important;} '
            '*::-webkit-scrollbar-corner {background: transparent;} '
            '.quantru-panel,.chat-list,dialog,textarea,.llama-settings-body,.thinking-text,.code-block pre,.markdown table,.katex-display,.markdown eqn,.shell-run-output {overscroll-behavior: contain !important;}',
            WebKit.UserContentInjectedFrames.TOP_FRAME,WebKit.UserStyleLevel.USER,None,None)
        self.view.get_user_content_manager().add_style_sheet(native_css)
        scroll_script=WebKit.UserScript.new((ROOT/'native-scroll.js').read_text(),
            WebKit.UserContentInjectedFrames.TOP_FRAME,WebKit.UserScriptInjectionTime.END,[URL+'*'],None)
        self.view.get_user_content_manager().add_script(scroll_script)
        manager=self.view.get_user_content_manager()
        self.preview_keyboard=False
        if manager.register_script_message_handler('focusPreview','quantru-focus'):
            manager.connect('script-message-received::focusPreview',self.focus_preview_changed)
            manager.add_script(WebKit.UserScript.new_for_world(
                (ROOT/'native-focus.js').read_text(),
                WebKit.UserContentInjectedFrames.TOP_FRAME,WebKit.UserScriptInjectionTime.END,
                'quantru-focus',['http://127.0.0.1/*'],None))
            keyboard=Gtk.EventControllerKey.new()
            keyboard.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            keyboard.connect('key-pressed',self.native_tab)
            self.view.add_controller(keyboard)

        if manager.register_script_message_handler_with_reply('modelPicker','quantru-picker'):
            manager.connect('script-message-with-reply-received::modelPicker',self.choose_model)
            manager.add_script(WebKit.UserScript.new_for_world(
                (ROOT/'native-model-picker.js').read_text(),
                WebKit.UserContentInjectedFrames.TOP_FRAME,WebKit.UserScriptInjectionTime.END,
                'quantru-picker',['http://127.0.0.1/*'],None))
        background=Gdk.RGBA()
        background.parse('#242424')
        self.view.set_background_color(background)
        settings=self.view.get_settings()
        settings.set_hardware_acceleration_policy(WebKit.HardwareAccelerationPolicy.NEVER)
        settings.set_default_font_family('Noto Sans')
        settings.set_sans_serif_font_family('Noto Sans')
        settings.set_monospace_font_family('DejaVu Sans Mono')
        settings.set_enable_media_stream(True)
        settings.set_enable_webaudio(True)
        settings.set_javascript_can_access_clipboard(True)
        self.view.connect('permission-request',self.permission)
        self.view.connect('decide-policy',self.navigation)
        self.view.connect('load-failed',self.load_failed)
        self.view.connect('web-process-terminated',self.web_terminated)
        self.view.connect('load-changed',self.load_changed)
        self.stack.add_named(self.view,'chat')
        self.stack.set_visible_child_name('waiting')
        action=Gio.SimpleAction.new('reload',None)
        action.connect('activate',lambda *_:self.view.reload())
        self.add_action(action)
        self.set_accels_for_action('app.reload',['<Control>r'])
        self.window.present()
        try:self.tray=Tray(self,APP_ID)
        except GLib.Error as e:print("Tray unavailable:",e.message,flush=True)
        self.start_backend()

    def start_backend(self):
        if self.stopping:return
        self.server_paused=False
        if self.tray:self.tray.set_running(True)
        if self.poll_source:
            GLib.source_remove(self.poll_source)
            self.poll_source=0
        self.retry.set_visible(False)
        self.waiting.set_title('Starting Quantru')
        self.waiting.set_description('Connecting to the local server…')
        self.stack.set_visible_child_name('waiting')
        self.start_time=time.monotonic()
        if web_available():
            self.view.load_uri(URL)
            return
        try:
            with urllib.request.urlopen(URL+'__version',timeout=.5):
                self.show_error('Another Quantru installation is using port 8765. Close it before opening this installation.')
                return
        except OSError:pass
        if self.server is None or self.server.poll() is not None:
            try:
                self.server=subprocess.Popen([sys.executable,'-B','-u',str(ROOT/'server.py')],cwd=ROOT,start_new_session=True)
            except OSError as e:
                self.show_error(str(e))
                return
        self.poll_source=GLib.timeout_add(250,self.poll_backend)

    def poll_backend(self):
        if web_available():
            self.poll_source=0
            self.view.load_uri(URL)
            return GLib.SOURCE_REMOVE
        if (self.server and self.server.poll() is not None) or time.monotonic()-self.start_time>25:
            self.poll_source=0
            self.show_error('The local server did not start. Check the terminal output and retry.')
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def close_window(self,window):
        # Without a working tray, close normally rather than hiding the
        # only visible way to quit or control the server.
        if not self.tray or not self.tray.available:return False
        if not self.hidden_hold:
            self.hold()
            self.hidden_hold=True
        window.hide()
        return True

    def tray_lost(self):
        if self.hidden_hold:self.tray_open()

    def tray_open(self):
        if self.window:self.window.present()
        if self.hidden_hold:
            self.hidden_hold=False
            self.release()
        return False

    def tray_toggle_server(self):
        if self.stopping:return False
        if self.server_paused or (not web_available() and (self.server is None or self.server.poll() is not None)):
            self.start_backend()
            return False
        if not web_available() or backend_status() not in ('ok','sleeping'):
            self.toast('Wait until the current request or model loading finishes.')
            return False
        if self.server is None or self.server.poll() is not None:
            self.toast('Server started outside this window. Close it from its original terminal.')
            return False
        self.stopping=True
        self.server_paused=True
        self.view.stop_loading()
        self.server.terminate()
        self.waiting.set_title('Server stopped')
        self.waiting.set_description('Start the server to continue using Quantru.')
        self.retry.set_label('Start server')
        self.retry.set_visible(False)
        self.stack.set_visible_child_name('waiting')
        GLib.timeout_add(200,self.poll_stopped)
        return False

    def poll_stopped(self):
        if self.server and self.server.poll() is None:return GLib.SOURCE_CONTINUE
        self.server=None
        self.stopping=False
        self.retry.set_visible(True)
        if self.tray:self.tray.set_running(False)
        return GLib.SOURCE_REMOVE

    def tray_quit(self):
        if self.hidden_hold:
            self.hidden_hold=False
            self.release()
        self.quit()
        return False

    def show_error(self,message):
        self.retry.set_label('Retry')
        if self.tray:self.tray.set_running(False)
        self.waiting.set_title('Quantru unavailable')
        self.waiting.set_description(message)
        self.retry.set_visible(True)
        self.stack.set_visible_child_name('waiting')

    def load_changed(self,view,event):
        if event==WebKit.LoadEvent.STARTED:self.preview_keyboard=False
        if not self.server_paused and event==WebKit.LoadEvent.FINISHED and view.get_uri() and view.get_uri().startswith(URL):
            self.stack.set_visible_child_name('chat')
            print('Native Quantru loaded:',view.get_uri(),flush=True)

    def load_failed(self,view,event,uri,error):
        if not self.server_paused and uri.startswith(URL):self.show_error(error.message)
        return True

    def web_terminated(self,view,reason):
        self.show_error('The web view stopped. Retry to reconnect to your saved chats.')

    def toast(self,text):
        self.overlay.add_toast(Adw.Toast.new(text))

    def permission(self,view,request):
        if not (view.get_uri() or '').startswith(URL):
            request.deny()
            return True
        if isinstance(request,WebKit.UserMediaPermissionRequest):
            if not request.get_property('is-for-audio-device') or request.get_property('is-for-video-device'):
                request.deny()
            elif self.audio_allowed:request.allow()
            else:
                dialog=Adw.AlertDialog(heading='Allow microphone?',body='Quantru uses your microphone for local speech transcription.')
                dialog.add_response('deny','Cancel')
                dialog.add_response('allow','Allow')
                dialog.set_default_response('allow')
                dialog.set_close_response('deny')
                def answered(_dialog,response):
                    self.audio_allowed=response=='allow'
                    if self.audio_allowed:request.allow()
                    else:request.deny()
                dialog.connect('response',answered)
                dialog.present(self.window)
            return True
        if isinstance(request,WebKit.ClipboardPermissionRequest):
            request.allow()
            return True
        if isinstance(request,WebKit.DeviceInfoPermissionRequest) and self.audio_allowed:
            request.allow()
            return True
        request.deny()
        return True

    def navigation(self,view,decision,kind):
        if kind not in (WebKit.PolicyDecisionType.NAVIGATION_ACTION,WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):return False
        action=decision.get_navigation_action()
        uri=action.get_request().get_uri() or ''
        if kind==WebKit.PolicyDecisionType.NAVIGATION_ACTION and (uri.startswith(URL) or uri.startswith(('about:','blob:','data:'))):return False
        decision.ignore()
        if action.is_user_gesture() and uri.startswith(('http://','https://')):
            try:Gio.AppInfo.launch_default_for_uri(uri,None)
            except GLib.Error as e:self.toast(e.message)
        return True

    def focus_preview_changed(self,manager,value):
        if (self.view.get_uri() or '').startswith(URL):
            self.preview_keyboard=value.to_boolean()

    def native_tab(self,controller,keyval,keycode,state):
        if self.preview_keyboard or not (self.view.get_uri() or '').startswith(URL):return False
        if keyval not in (Gdk.KEY_Tab,Gdk.KEY_ISO_Left_Tab,Gdk.KEY_KP_Tab):return False
        if state & (Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK):return False
        reverse=keyval==Gdk.KEY_ISO_Left_Tab or bool(state & Gdk.ModifierType.SHIFT_MASK)
        self.view.evaluate_javascript('window.quantruMoveFocus?.('+('true' if reverse else 'false')+')',-1,'quantru-focus',None,None,None)
        return True

    def choose_model(self,manager,value,reply):
        if not (self.view.get_uri() or '').startswith(URL) or getattr(self,'model_picker_open',False):
            reply.return_error_message('File selector unavailable.')
            return True
        try:
            data=json.loads(value.to_json(0))
            kind=data['kind']
            filters={
                'gguf':('GGUF models',('*.gguf',)),
                'image':('Image models',('*.gguf','*.safetensors')),
                'lora':('LoRA adapters',('*.safetensors','*.ckpt')),
            }
            name,patterns=filters[kind]
            current=data.get('current','')
            if not isinstance(current,str) or len(current)>4096:current=''
        except (ValueError,TypeError,KeyError):
            reply.return_error_message('Invalid file selection request.')
            return True
        dialog=Gtk.FileDialog(title='Choose model file',modal=True)
        filter_=Gtk.FileFilter()
        filter_.set_name(name)
        for pattern in patterns:filter_.add_pattern(pattern)
        filter_list=Gio.ListStore.new(Gtk.FileFilter)
        filter_list.append(filter_)
        dialog.set_filters(filter_list)
        dialog.set_default_filter(filter_)
        try:
            path=pathlib.Path(current).expanduser()
            if current and path.is_absolute():
                if path.is_file():dialog.set_initial_file(Gio.File.new_for_path(str(path)))
                elif path.parent.is_dir():dialog.set_initial_folder(Gio.File.new_for_path(str(path.parent)))
        except (OSError,ValueError,RuntimeError):pass
        self.model_picker_open=True
        pending=reply.ref()
        context=value.get_context()
        def selected(d,result):
            self.model_picker_open=False
            try:
                file=d.open_finish(result)
                chosen=file.get_path() if file else None
                if chosen and pathlib.Path(chosen).suffix.lower() not in {pat[1:] for pat in patterns}:chosen=None
                pending.return_value(JSC.Value.new_string(context,chosen) if chosen else JSC.Value.new_null(context))
            except GLib.Error:
                pending.return_value(JSC.Value.new_null(context))
        dialog.open(self.window,None,selected)
        return True

    def download_started(self,session,download):
        self.downloads.add(download)
        download.connect('decide-destination',self.choose_destination)
        download.connect('finished',lambda d:self.downloads.discard(d))
        def failed(d,error):
            self.downloads.discard(d)
            if not error.matches(WebKit.download_error_quark(),WebKit.DownloadError.CANCELLED_BY_USER):
                self.toast('Download failed: '+error.message)
        download.connect('failed',failed)

    def choose_destination(self,download,filename):
        dialog=Gtk.FileDialog(title='Save file',initial_name=pathlib.Path(filename).name or 'download')
        folder=GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if folder:dialog.set_initial_folder(Gio.File.new_for_path(folder))
        def selected(dialog,result):
            try:
                file=dialog.save_finish(result)
                download.set_allow_overwrite(True)
                download.set_destination(file.get_uri())
            except GLib.Error:
                download.cancel()
        dialog.save(self.window,None,selected)
        return True

    def do_shutdown(self):
        if self.tray:self.tray.close()
        if self.poll_source:GLib.source_remove(self.poll_source)
        if self.server and self.server.poll() is None:
            # Never interrupt a request from a paired phone or an existing browser.
            if backend_status() in ('ok','sleeping'):
                self.server.terminate()
                try:self.server.wait(timeout=12)
                except subprocess.TimeoutExpired:print('Server shutdown still pending.',flush=True)
            else:print('Quantru server remains running because it is busy or starting.',flush=True)
        Adw.Application.do_shutdown(self)

if __name__=='__main__':
    sys.exit(Quantru().run(sys.argv))
