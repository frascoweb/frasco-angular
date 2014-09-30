from frasco import Feature, action, Blueprint, View, render_template, current_context, command, hook
from frasco.utils import remove_yaml_frontmatter
from frasco.templating import FileLoader
import os
import json
import re


class AngularView(View):
    def __init__(self, template=None, **kwargs):
        view_attrs = ('name', 'url', 'methods', 'url_rules')
        self.route_options = { k: kwargs.pop(k) for k in kwargs.keys() if k not in view_attrs}
        super(AngularView, self).__init__(**kwargs)
        self.template = template

    def dispatch_request(self, *args, **kwargs):
        return render_template("angular_layout.html", **current_context.vars)


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
                "app_file": "app/app.js", # set to False to not generate an app.js
                "app_module": "app",
                "app_deps": [],
                "partials_dir": "app/partials",
                "directives_file": "app/directives/auto.js",
                "directives_module": "directives",
                "views_dir": "app/views",
                "routes_file": "app/routes.js",
                "routes_module": "routes",
                "services_file": "app/services/auto.js",
                "services_module": "services",
                "disable_reloading_endpoints": False}

    def init_app(self, app):
        self.app = app
        self.built = False
        if not self.options["static_dir"]:
            self.options["static_dir"] = app.static_folder
        if not self.options["static_url_path"]:
            self.options["static_url_path"] = app.static_url_path

        app.features.assets.expose_package("frasco_angular", __name__)
        app.assets.register({
            "angular-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/1.2.20/angular.min.js"],
            "angular-route-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/1.2.20/angular-route.min.js"],
            "angular-resource-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/1.2.20/angular-resource.min.js"],
            "angular-animate-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/1.2.20/angular-animate.min.js"],
            "angular-cookies-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/1.2.20/angular-cookies.min.js"],
            "angular-loader-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/1.2.20/angular-loader.min.js"],
            "angular-sanitize-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/1.2.20/angular-sanitize.min.js"],
            "angular-touch-cdn": [
                "https://cdnjs.cloudflare.com/ajax/libs/angular.js/1.2.20/angular-touch.min.js"],
            "angular-frasco": [
                "frasco_angular/angular-frasco.js"]})

        app.jinja_env.loader.bottom_loaders.append(FileLoader(
            os.path.join(os.path.dirname(__file__), "layout.html"), "angular_layout.html"))

        if not self.options["disable_reloading_endpoints"]:
            # adding the url rule ensure that we don't need to reload the app to regenerate the
            # partial file. partial files are still generated when the app starts but will then
            # be served by this endpoint and be generated on the fly
            # note: we don't need to the same for views as a change triggers the reloader
            app.add_url_rule(self.options["static_url_path"] + "/" + self.options["partials_dir"] + "/<macro>.html",
                endpoint="angular_partial", view_func=self.extract_macro)

    @property
    def assets(self):
        if "angular-app" not in self.app.assets:
            self.app.assets.register("angular-app")
        return self.app.assets["angular-app"]

    @command()
    def build(self):
        files = []
        files.extend(self.build_directives())
        files.extend(self.build_routes())
        files.extend(self.build_services())
        files.extend(self.build_app())
        for filename, source in files:
            if not os.path.exists(os.path.dirname(filename)):
                os.makedirs(os.path.dirname(filename))
            with open(filename, 'w') as f:
                f.write(source)

    @command()
    def clean(self):
        files = []
        files.extend(self.build_directives())
        files.extend(self.build_routes())
        files.extend(self.build_services())
        files.extend(self.build_app())
        for filename, source in files:
            if os.path.exists(filename):
                os.unlink(filename)

    @hook()
    def before_request(self):
        if not self.built:
            self.build()
            self.built = True

    def build_routes(self):
        files = []
        views = []
        for name, bp in self.app.blueprints.iteritems():
            if isinstance(bp, Blueprint):
                for v in bp.views.itervalues():
                    if isinstance(v, AngularView):
                        views.append((bp.url_prefix, v))

        base_url = self.options["static_url_path"] + "/" + self.options["views_dir"] + "/"
        when_tpl = "$routeProvider.when('%s', %s);"
        routes = []
        for url_prefix, view in views:
            files.append(self.export_view(view.template))
            for url, options in view.url_rules:
                spec = dict(view.route_options, templateUrl=base_url + view.template)
                if url_prefix:
                    url = url_prefix + url
                url = convert_url_args(url)
                routes.append(when_tpl % (url, json.dumps(spec)))

        routes.append("$routeProvider.otherwise({redirectTo: function(params, path, search) { window.location.href = path; }});")
        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n\nangular.module('%s',"
                  "['ngRoute']).config(['$routeProvider', '$locationProvider',\n"
                  "    function($routeProvider, $locationProvider) {\n        $locationProvider.html5Mode(true);\n"
                  "        %s\n    }\n]);\n") % (self.options["routes_module"], "\n        ".join(routes))
        filename = os.path.join(self.options["static_dir"], self.options["routes_file"])
        files.append((filename, module))
        self.assets.append("@angular-route-cdn", self.options["routes_file"])
        self.options["app_deps"].append(self.options["routes_module"])
        return files

    def export_view(self, filename):
        pathname = os.path.join(self.app.template_path, filename)
        with open(pathname) as f:
            source = remove_yaml_frontmatter(f.read())
        dest = os.path.join(self.options["static_dir"], self.options["views_dir"], filename)
        return (dest, source)

    def build_directives(self):
        files = []
        directives = {}
        for macro in self.options["export_macros"]:
            filename, source, directives[macro] = self.export_macro(macro)
            files.append((filename, source))

        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n"
                  "\nvar directives = angular.module('%s', []);\n\n") % self.options["directives_module"]
        for name, options in directives.iteritems():
            name = options.pop("name", name)
            module += "directives.directive('%s', function() {\nreturn %s;\n});\n\n" % (name, json.dumps(options, indent=4))

        filename = os.path.join(self.options["static_dir"], self.options["directives_file"])
        files.append((filename, module))
        self.assets.append(self.options["directives_file"])
        self.options["app_deps"].append(self.options["directives_module"])
        return files

    def export_macro(self, macro):
        partial, options = self.extract_macro(macro, True)
        filename = os.path.join(self.options["static_dir"], self.options["partials_dir"], macro + ".html")
        url = self.options["static_url_path"] + "/" + self.options["partials_dir"] + "/" + macro + ".html"
        options["templateUrl"] = url
        return (filename, partial.strip(), options)

    def extract_macro(self, macro, with_options=False):
        template = self.app.jinja_env.macros.resolve_template(macro)
        if not template:
            raise Exception("Macro '%s' cannot be exported to angular because it does not exist" % macro)
        (source, _, __) = self.app.jinja_env.loader.get_source(self.app.jinja_env, template)

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
        self.assets.append(self.options["app_file"])
        return [(os.path.join(self.options["static_dir"], self.options["app_file"]), module)]

    def build_services(self):
        if not self.options["services_file"]:
            return []
        filename = os.path.join(self.options["static_dir"], self.options["services_file"])
        module = ("/* This file is auto-generated by frasco-angular. DO NOT MODIFY. */\n'use strict';\n"
                  "\nvar services = angular.module('%s', ['frasco']);\n") % self.options["services_module"]

        for name, srv in self.app.services.iteritems():
            endpoints = {}
            for view in srv.views:
                endpoints[view.name] = [convert_url_args(view.url_rules[0][0]), view.func.view_args]
            module += ("\nservices.factory('%s', ['frascoServiceFactory', function(frascoServiceFactory) {\n"
                       "return frascoServiceFactory.make('%s', [], %s);\n}]);\n") % \
                        (name, self.app.services_url_prefix, json.dumps(endpoints, indent=2))

        self.assets.append("@angular-frasco", self.options["services_file"])
        return [(filename, module)]