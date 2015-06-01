from frasco import (Feature, action, Blueprint, View, render_template,\
                    current_context, command, hook, current_app, signal)
from frasco.utils import remove_yaml_frontmatter
from frasco.templating import get_template_source
import os
import json
import re
import hashlib
import uuid
from jinja2 import PackageLoader
from jinja2.ext import Extension


class AngularView(View):
    def __init__(self, template=None, layout=None, angular_url=None, **kwargs):
        view_attrs = ('name', 'url', 'methods', 'url_rules')
        self.angular_url = angular_url
        self.route_options = { k: kwargs.pop(k) for k in kwargs.keys() if k not in view_attrs}
        super(AngularView, self).__init__(**kwargs)
        self.template = template
        self.layout = layout

    def dispatch_request(self, *args, **kwargs):
        layout = self.layout or current_app.features.angular.options['views_layout']
        return render_template(layout, **current_context.vars)


_endmacro_re = re.compile(r"\{%-?\s*endmacro\s*%\}")
_ngdirective_re = re.compile(r"\{#\s*ngdirective:(.+)#\}")
_url_arg_re = re.compile(r"<([a-z]:)?([a-z0-9_]+)>")


def convert_url_args(url):
    return _url_arg_re.sub(r":\2", url)


class AngularFeature(Feature):
    name = "angular"
    requires = ["assets"]
    view_files = [("*.ng.html", AngularView)]
    ignore_attributes = ['assets']
    defaults = {"export_macros": [],
                "static_dir": None, # defaults to app.static_folder
                "static_url_path": None, # defaults to app.static_url_path
                "auto_assets": True,
                "base_layout": "frasco_layout.html",
                "app_dir": "app/",
                "app_file": "app.js", # set to False to not generate an app.js
                "app_module": "app",
                "app_deps": [],
                "partials_dir": "partials",
                "directives_file": "directives/auto.js",
                "directives_module": "directives",
                "directives_name": "%s",
                "auto_add_directives_module": True,
                "views_dir": "views",
                "routes_file": "routes.js",
                "routes_module": "routes",
                "auto_add_routes_module": True,
                "views_layout": "angular_layout.html",
                "services_file": "services/auto.js",
                "services_module": "services",
                "services_name": "%s",
                "auto_add_services_module": True,
                "disable_reloading_endpoints": False,
                "auto_build": True,
                "angular_version": "1.3.3",
                "add_app_dir_in_babel_extract": True}

    build_all_signal = signal('angular_build_all')
    before_build_write_signal = signal('angular_before_build_write')
    before_clean_signal = signal('angular_before_clean')

    def init_app(self, app):
        self.app = app
        self.built = False
        if not self.options["static_dir"]:
            self.options["static_dir"] = app.static_folder
        if not self.options["static_url_path"]:
            self.options["static_url_path"] = app.static_url_path

        app.features.assets.expose_package("frasco_angular", __name__)
        version = self.options['angular_version']
        app.assets.register({
            "angular-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/%s/angular.min.js" % version],
            "angular-route-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/%s/angular-route.min.js" % version],
            "angular-resource-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/%s/angular-resource.min.js" % version],
            "angular-animate-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/%s/angular-animate.min.js" % version],
            "angular-cookies-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/%s/angular-cookies.min.js" % version],
            "angular-loader-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/%s/angular-loader.min.js" % version],
            "angular-sanitize-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/%s/angular-sanitize.min.js" % version],
            "angular-touch-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/%s/angular-touch.min.js" % version],
            "angular-frasco": [
                {"output": "angular-frasco.min.js", "filters": "jsmin",
                 "contents": ["frasco_angular/angular-frasco.js"]}]})

        app.jinja_env.loader.bottom_loaders.append(PackageLoader(__name__))
        app.jinja_env.loader.set_layout_alias("angular_app_layout.html")

        self.auto_assets_pkg = app.assets.register("angular-auto-assets",
            {"output": "frasco-auto-angular",
             "contents": [{"filters": "jsmin", "contents": ["frasco_angular/angular-frasco.js"]}]})
        if self.options['auto_assets']:
            app.features.assets.add_default("@angular-cdn", "@angular-route-cdn",
                "@angular-auto-assets")

        signal('before_assets_build').connect(lambda *args: self.build(), weak=False)

        if not self.options["disable_reloading_endpoints"]:
            # adding the url rule ensure that we don't need to reload the app to regenerate the
            # partial file. partial files are still generated when the app starts but will then
            # be served by this endpoint and be generated on the fly
            # note: we don't need to the same for views as a change triggers the reloader
            app.add_url_rule(self.options["static_url_path"] + "/" + self.options["partials_dir"] + "/<macro>.html",
                endpoint="angular_partial", view_func=self.extract_macro)

        if app.features.exists('babel') and self.options['add_app_dir_in_babel_extract']:
            app.features.babel.add_extract_dir(os.path.join(self.options['static_dir'], self.options['app_dir']),
                '.', ['frasco_angular.AngularCompatExtension'], [('javascript:**.js', {})])

    @command()
    def build(self):
        files = self.build_all()
        self.before_build_write_signal.send(self, files=files)
        for filename, source in files:
            if not os.path.exists(os.path.dirname(filename)):
                os.makedirs(os.path.dirname(filename))
            with open(filename, 'w') as f:
                f.write(source)

    @command()
    def clean(self):
        files = self.build_all()
        self.before_clean_signal.send(self, files=files)
        for filename, source in files:
            if os.path.exists(filename):
                os.unlink(filename)

    @hook()
    def before_request(self):
        if not self.built and self.options["auto_build"]:
            self.build()
            self.built = True

    def build_all(self):
        files = []
        files.extend(self.build_directives())
        files.extend(self.build_routes())
        files.extend(self.build_services())
        files.extend(self.build_app())
        self.build_all_signal.send(self, files=files)
        return files

    def build_routes(self):
        if not self.options['routes_file']:
            return []
        files = []
        views = []
        for v in self.app.views.itervalues():
            if isinstance(v, AngularView):
                views.append((None, v))
        for name, bp in self.app.blueprints.iteritems():
            if isinstance(bp, Blueprint):
                for v in bp.views.itervalues():
                    if isinstance(v, AngularView):
                        views.append((bp.url_prefix, v))

        base_url = self.options["static_url_path"] + "/" + self.options['app_dir'] + "/" + self.options["views_dir"] + "/"
        when_tpl = "$routeProvider.when('%s', %s);"
        version = hashlib.sha1(str(uuid.uuid4())).hexdigest()[:8]
        routes = []
        for url_prefix, view in views:
            files.append(self.export_view(view.template))
            spec = dict(view.route_options, templateUrl=base_url + view.template + '?' + version)
            if view.angular_url:
                routes.append(when_tpl % (view.angular_url, json.dumps(spec)))
            else:
                for url, options in view.url_rules:
                    if url_prefix:
                        url = url_prefix + url
                    routes.append(when_tpl % (convert_url_args(url), json.dumps(spec)))

        routes.append("$routeProvider.otherwise({redirectTo: function(params, path, search) { window.location.href = path; }});")
        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n\n"
                  "function versionizeUrl(url) {\n  return url + '?%s';\n};\n\n"
                  "angular.module('%s',['ngRoute']).config(['$routeProvider', '$locationProvider',\n"
                  "  function($routeProvider, $locationProvider) {\n    $locationProvider.html5Mode(true);\n"
                  "    %s\n  }\n]);\n") % (version, self.options["routes_module"], "\n        ".join(routes))
        filename = os.path.join(self.options['app_dir'], self.options["routes_file"])
        files.append((os.path.join(self.options["static_dir"], filename), module))
        self.auto_assets_pkg.append({"filters": "jsmin", "contents": [filename]})
        if self.options['auto_add_routes_module']:
            self.options["app_deps"].append(self.options["routes_module"])
        return files

    def export_view(self, filename):
        source = remove_yaml_frontmatter(get_template_source(self.app, filename))
        dest = os.path.join(self.options["static_dir"], self.options['app_dir'],
                            self.options["views_dir"], filename)
        return (dest, source)

    def build_directives(self):
        files = []
        directives = {}
        for macro in self.options["export_macros"]:
            filename, source, directives[macro] = self.export_macro(macro)
            files.append((filename, source))

        if not files:
            return files

        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n"
                  "\n(function() {\n\nvar directives = angular.module('%s', []);\n\n") % self.options["directives_module"]
        for name, options in directives.iteritems():
            name = options.pop("name", name)
            module += "directives.directive('%s', function() {\nreturn %s;\n});\n\n" % \
                (self.options['directives_name'] % name, json.dumps(options, indent=4))

        module += "})();";
        filename = os.path.join(self.options["app_dir"], self.options["directives_file"])
        files.append((os.path.join(self.options["static_dir"], filename), module))
        self.auto_assets_pkg({"filters": "jsmin", "contents": [filename]})
        if self.options['auto_add_directives_module']:
            self.options["app_deps"].append(self.options["directives_module"])
        return files

    def export_macro(self, macro):
        partial, options = self.extract_macro(macro, True)
        filename = os.path.join(self.options["static_dir"], self.options['app_dir'],
                                self.options["partials_dir"], macro + ".html")
        url = self.options["static_url_path"] + "/" + self.options['app_dir'] + "/" \
            + self.options["partials_dir"] + "/" + macro + ".html"
        options["templateUrl"] = url
        return (filename, partial.strip(), options)

    def extract_macro(self, macro, with_options=False):
        template = self.app.jinja_env.macros.resolve_template(macro)
        if not template:
            raise Exception("Macro '%s' cannot be exported to angular because it does not exist" % macro)
        source = get_template_source(self.app, template)

        m = re.search(r"\{%\s*macro\s+" + re.escape(macro), source)
        if not m:
            raise Exception("Macro '%s' not found in template %s" % (macro, template))
        start = source.find("%}", m.start()) + 2
        end = _endmacro_re.search(source, start).start()
        partial = source[start:end]

        options = {}
        m = _ngdirective_re.search(partial)
        if m:
            options = json.loads(m.group(1))
            partial = partial.replace(m.group(0), "")
        if with_options:
            return (partial, options)
        return partial

    def build_app(self):
        if not self.options["app_file"]:
            return []
        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n"
                  "\nangular.module('%s', [\n  '%s'\n]);\n") % (self.options["app_module"], "',\n  '".join(self.options["app_deps"]))
        filename = os.path.join(self.options['app_dir'], self.options['app_file'])
        self.auto_assets_pkg.append({"filters": "jsmin", "contents": [filename]})
        return [(os.path.join(self.options["static_dir"], filename), module)]

    def build_services(self):
        if not self.options["services_file"]:
            return []
        filename = os.path.join(self.options["app_dir"], self.options["services_file"])
        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n"
                  "\n(function() {\n\nvar services = angular.module('%s', ['frasco']);\n") % self.options["services_module"]

        for name, srv in self.app.services.iteritems():
            endpoints = {}
            for view in srv.views:
                args = []
                if hasattr(view.func, '_request_params'):
                    for p in reversed(view.func._request_params):
                        args.extend(p.names)
                endpoints[view.name] = [convert_url_args(view.url_rules[0][0]), args]
            module += ("\nservices.factory('%s', ['frascoServiceFactory', function(frascoServiceFactory) {\n"
                       "return frascoServiceFactory.make('%s', [], %s);\n}]);\n") % \
                        (self.options['services_name'] % name, self.app.services_url_prefix,\
                         json.dumps(endpoints, indent=2))

        module += "\n})();";
        self.auto_assets_pkg.append({"filters": "jsmin", "contents": [filename]})
        if self.options["auto_add_services_module"]:
            self.options["app_deps"].append(self.options["services_module"])
        return [(os.path.join(self.options["static_dir"], filename), module)]


class AngularCompatExtension(Extension):
    """Jinja extension that does the bare minimum into making angular templates
    parsable by Jinja so gettext strings can be extacted.
    Removes angular one-time binding indicators and javascript ternary operator.
    """
    special_chars_re = re.compile(r"'[^']*'|\"[^\"]+\"|\{[^{]+\}|([?:!&|$=]{1,3})")
    replacements = {'!': ' not ', '$': '', '=': '=', '==': '==',
                    '===': '==', '!=': '!=', '!==': '!=', '&&': ' and ', '||': ' or '}

    def process_expression(self, source, start):
        p = start
        end = p
        while True:
            end = source.find('}}', p)
            m = self.special_chars_re.search(source, p, end)
            if not m:
                break
            if m.group(1) is None:
                p = m.end(0)
                continue
            repl = self.replacements.get(m.group(1), ' or ')
            p = m.start(1) + len(repl)
            source = source[:m.start(1)] + repl + source[m.end(1):]
        return source, end + 2

    def preprocess(self, source, name, filename=None):
        source = source.replace('{{::', '{{')
        p = 0
        while True:
            p = source.find('{{', p)
            if p == -1:
                break
            source, p = self.process_expression(source, p + 2)
        return source