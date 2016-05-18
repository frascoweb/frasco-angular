from frasco import (Feature, action, Blueprint, View, render_template,\
                    current_context, command, hook, current_app, signal)
from frasco.utils import remove_yaml_frontmatter
from frasco.templating import get_template_source
import os
import json
import re
import hashlib
import uuid
import json
from jinja2 import PackageLoader
from jinja2.ext import Extension
import htmlmin
import codecs


class AngularView(View):
    def __init__(self, name=None, url=None, template=None, layout=None, angular_url=None, **kwargs):
        view_attrs = ('methods', 'url_rules')
        self.angular_url = angular_url
        self.route_options = { k: kwargs.pop(k) for k in kwargs.keys() if k not in view_attrs}
        super(AngularView, self).__init__(name=name, url=url, **kwargs)
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
                "use_layout": True,
                "base_layout": "frasco_layout.html",
                "app_dir": "app",
                "app_file": "app.js", # set to False to not generate an app.js
                "app_module": "app",
                "app_var": "app",
                "app_deps": [],
                "partials_dir": "partials",
                "directives_file": "directives/auto.js",
                "directives_module": "directives",
                "directives_name": "%s",
                "auto_add_directives_module": True,
                "views_dir": "views",
                "routes_file": "routes.js",
                "routes_module": "routes",
                "routes": [],
                "auto_add_routes_module": True,
                "views_layout": "angular_layout.html",
                "services_file": "services/auto.js",
                "services_module": "services",
                "services_name": "%s",
                "auto_add_services_module": True,
                "templates_file": None,
                "templates_module": "templatesCache",
                "disable_templates_cache": None, # app.debug
                "auto_add_templates_module": True,
                "templates_matcher": r".*\.html$",
                "disable_reloading_endpoints": False,
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
        if self.options["use_layout"]:
            app.jinja_env.loader.set_layout_alias("angular_app_layout.html")

        self.auto_assets_pkg = app.assets.register("angular-auto-assets",
            {"output": "frasco-auto-angular",
             "contents": [{"filters": "jsmin", "contents": ["frasco_angular/angular-frasco.js"]}]})
        if self.options['auto_assets']:
            app.features.assets.add_default("@angular-cdn", "@angular-route-cdn",
                "@angular-auto-assets")

        app.features.assets.register_assets_builder(self.build)

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
            with codecs.open(filename, "w", "utf-8") as f:
                f.write(source)

    @command()
    def clean(self):
        files = self.build_all()
        self.before_clean_signal.send(self, files=files)
        for filename, source in files:
            if os.path.exists(filename):
                os.unlink(filename)

    def build_all(self, version=None):
        if not version:
            version = hashlib.sha1(str(uuid.uuid4())).hexdigest()[:8]
        files = []
        files.extend(self.build_directives(version))
        files.extend(self.build_routes(version))
        files.extend(self.build_services(version))
        files.extend(self.build_templates(version))
        files.extend(self.build_app(version))
        self.build_all_signal.send(self, files=files, version=version)
        return files

    def _iter_angular_views(self):
        for v in self.app.views.itervalues():
            if isinstance(v, AngularView):
                yield (None, v)
        for name, bp in self.app.blueprints.iteritems():
            if isinstance(bp, Blueprint):
                for v in bp.views.itervalues():
                    if isinstance(v, AngularView):
                        yield (bp.url_prefix, v)

    def build_routes(self, version):
        if not self.options['routes_file']:
            return []
        files = []

        base_url = self.options["static_url_path"] + "/" + self.options['app_dir'] + "/" + self.options["views_dir"] + "/"
        when_tpl = "$routeProvider.when('%s', %s);"
        routes = []
        for url_prefix, view in self._iter_angular_views():
            spec = dict(view.route_options)
            if view.template:
                files.append(self.export_view(view.template))
                spec['templateUrl'] = base_url + view.template
            if 'templateUrl' in spec:
                spec['templateUrl'] = spec['templateUrl'] + '?' + version
            if view.angular_url:
                routes.append(when_tpl % (view.angular_url, json.dumps(spec)))
            else:
                for url, options in view.url_rules:
                    if url_prefix:
                        url = url_prefix + url
                    routes.append(when_tpl % (convert_url_args(url), json.dumps(spec)))
        for spec in self.options["routes"]:
            if not isinstance(spec, dict) or 'url' not in spec:
                raise Exception('Wrong format for route definition')
            if 'templateUrl' in spec:
                spec['templateUrl'] = spec['templateUrl'] + '?' + version
            routes.append(when_tpl % (spec.pop('url'), json.dumps(spec)))

        routes.append("$routeProvider.otherwise({redirectTo: function(params, path, search) { window.location.href = path; }});")
        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n\n"
                  "function versionizeUrl(url) {\n  return url + '?%s';\n};\n\n"
                  "angular.module('%s', ['ngRoute']).config(['$routeProvider', '$locationProvider',\n"
                  "  function($routeProvider, $locationProvider) {\n    $locationProvider.html5Mode(true);\n"
                  "    %s\n  }\n]);\n") % (version, self.options["routes_module"], "\n    ".join(routes))
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

    def build_directives(self, version):
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

    def build_app(self, version):
        if not self.options["app_file"]:
            return []
        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n"
                  "\nvar %s = angular.module('%s', [\n  '%s'\n]);\n") % (self.options['app_var'],
                    self.options["app_module"], "',\n  '".join(self.options["app_deps"]))
        filename = os.path.join(self.options['app_dir'], self.options['app_file'])
        self.auto_assets_pkg.append({"filters": "jsmin", "contents": [filename]})
        return [(os.path.join(self.options["static_dir"], filename), module)]

    def build_services(self, version):
        if not self.options["services_file"]:
            return []
        filename = os.path.join(self.options["app_dir"], self.options["services_file"])
        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n"
                  "\n(function() {\n\nvar services = angular.module('%s', ['frasco']);\n") % self.options["services_module"]

        for name, srv in self.app.services.iteritems():
            endpoints = {}
            for view in srv.views:
                args = []
                if hasattr(view.func, 'request_params'):
                    for p in reversed(view.func.request_params):
                        args.extend(p.names)
                endpoints[view.name] = [convert_url_args(view.url_rules[-1][0]), args]
            module += ("\nservices.factory('%s', ['frascoServiceFactory', function(frascoServiceFactory) {\n"
                       "return frascoServiceFactory.make('%s', '%s', [], %s);\n}]);\n") % \
                        (self.options['services_name'] % name, name, self.app.services_url_prefix,\
                         json.dumps(endpoints, indent=2))

        module += "\n})();";
        self.auto_assets_pkg.append({"filters": "jsmin", "contents": [filename]})
        if self.options["auto_add_services_module"]:
            self.options["app_deps"].append(self.options["services_module"])
        return [(os.path.join(self.options["static_dir"], filename), module)]

    def build_templates(self, version):
        if not self.options["templates_file"]:
            return []

        module = [("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n"
                  "\nangular.module('%s', []).run(['$templateCache', function($templateCache) {") % self.options["templates_module"]]
        matcher = re.compile(self.options["templates_matcher"], re.I)
        done = set()

        def process_file(filename, path=None, content=None):
            if not path:
                pathname = filename
                path = os.path.dirname(filename)
                filename = os.path.basename(filename)
            else:
                pathname = os.path.join(path, filename)
            relname = self.options["static_url_path"] + "/" + os.path.relpath(path, self.options["static_dir"]) + "/" + filename
            if pathname not in done and matcher.match(relname):
                if not content:
                    with codecs.open(pathname, 'r', 'utf-8') as f:
                        content = f.read()
                module.append("  $templateCache.put('%s?%s', %s);" % (relname, version, json.dumps(htmlmin.minify(content))))
                done.add(pathname)

        disable = self.options["disable_templates_cache"]
        if (disable is None and not self.app.debug) or disable is False:
            for url_prefix, view in self._iter_angular_views():
                if view.template:
                    dest, source = self.export_view(view.template)
                    process_file(dest, content=source)
            for path, dirnames, filenames in os.walk(os.path.join(self.options["static_dir"], self.options['app_dir'])):
                for filename in filenames:
                    process_file(filename, path)

        module = "\n".join(module) + "\n}]);"
        filename = os.path.join(self.options["app_dir"], self.options["templates_file"])
        self.auto_assets_pkg.append({"filters": "jsmin", "contents": [filename]})
        if self.options["auto_add_templates_module"]:
            self.options["app_deps"].append(self.options["templates_module"])
        return [(os.path.join(self.options["static_dir"], filename), module)]


class AngularCompatExtension(Extension):
    """Jinja extension that does the bare minimum into making angular templates
    parsable by Jinja so gettext strings can be extacted.
    Removes angular one-time binding indicators and javascript ternary operator.
    """
    special_chars_re = re.compile(r"'[^']*'|\"[^\"]+\"|(\{[^{]+\}|[?:!&|$=]{1,3})")
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
            if m.group(1).startswith('{'):
                repl = 'True'
            else:
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