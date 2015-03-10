# Frasco-Angular

[AngularJs](http://angularjs.org) integration with Frasco.

## Installation

    pip install frasco-angular

## Setup

Feature name: angular

Options:

 - *export_macros*: list of macro names to export as directives
 - *static_dir*: folder where assets are located (default: same as `app.static_folder`)
 - *static_url_path*: url where assets are located (default: same as `app.static_url_path`)
 - *auto_assets*: whether to include default assets automatically (see further)
 - *base_layout*: template from which *angular_app_layout.html* extends (default: *frasco_layout.html*)
 - *app_dir*: base directory for angular files relative to static dir (default: app)
 - *app_file*: filename relative to the app_dir of the application
   module to generate (default: app/app.js). Set to false to not generate.
 - *app_module*: name of the module for the application
 - *app_deps*: list of dependencies for the application module
 - *partials_dir*: folder relative to the app_dir where to store partials
   generated as part of exported macros (default: app/partials)
 - *directives_file*: filename relative to the app_dir where to store
   directives generated as part of exported macros (default: app/directives/auto.js)
 - *directives_module*: module name for directives from exported macros (default: directives)
 - *directives_name*: string template for directive names ("%s" will be replaced by directive name)
 - *views_dir*: folder relative to the app_dir where to store views (default: app/views)
 - *views_layout*: template filename of the layout for the views (default: angular_layout.html)
 - *routes_file*: filename relative to the app_dir for the router (default: app/routes.js)
 - *routes_module*: module name of the router
 - *services_file*: filename relative to the app_dir for the generated services
   (default: app/services/auto.js)
 - *services_module*: module name for the generated services (default: services)
 - *services_name*: string template for service names ("%s" will be replaced by the service name)
 - *disable_reloading_endpoints*: whether to create an endpoint which will allow automatic
   reloading of partials when the macro is updated (default: true)
 - *auto_build*: whether to automatically build the assets
 - *angular_version*: which angular version to use

## Assets

Some asets packages are included:

 - *angular-cdn*: angular.js from cdnjs
 - *angular-route-cdn*: angular-route from cdnjs
 - *angular-resource-cdn*: andular-resource from cdnjs
 - *angular-animate-cdn*: andular-animate from cdnjs
 - *angular-cookies-cdn*: andular-cookies from cdnjs
 - *angular-loader-cdn*: andular-loader from cdnjs
 - *angular-sanitize-cdn*: andular-sanitize from cdnjs
 - *angular-touch-cdn*: andular-touch from cdnjs
 - *angular-frasco*: Angular module which contains utils to integrate Frasco with Angular

When using an angular view (see further), the *angular-cdn* and *angular-app*
packages will be automatically included (unless *auto_assets* is false).
*angular-app* is the package you should use to add custom assets to your app.

## Views

Frasco-Angular blends Frasco views and Angular routes seamlessly. When using views
of type `frasco_angular.AngularView`, an endpoint will be registered on the python
side and a route will be registered in [angular-route](https://docs.angularjs.org/api/ngRoute).

`AngularView`s have the following options:

 - *template*: the template name associated to the view
 - *layout*: override the default layout
 - all standard frasco views options
 - angular-route options

Angular views cannot have any actions.

```python
from frasco_angular import AngularView
view = AngularView(url='/', template='index.html', controller='HomeCtrl')
```

Note than the template will not be processed by Jinja.

When the user accesses the url, the view layout will be rendered. Unless modified in
the config, the layout template is *angular_layout.html*. Frasco-Angular provides a
default one which extends *layout.html* and adds the *ng-app* directive to the `<html>` tag,
includes the relevant assets and adds an *ng-view* directive to the content block.

The generated angular-route config is stored in static/app/routes.js (unless modified
with the config) and automatically added to the *angular-app* package. If you navigate
to a path which is not registered in the router, it will exit the Angular app, and
set `window.location.href` to the new path.

When using declarative apps, you can create angular views using the *.ng.html* extension.

    ---
    url: /
    controller: HomeCtrl
    ---
    this is not a jinja template

## Services

Frasco-Angular will generate objects to easily access your services from your controllers.
For each service, a service object will be created. All methods from your services
decorated with `@expose` will be available on this services object. The client-side method
has the same argument as the server-side one but it returns an object with the following
methods:

 - `get(callback)`: data is passed as params, the callback is optional
 - `post(callback)`: data is passed in the body, the callback is optional
 - `put(callback)`: data is passed in the body, the callback is optional
 - `delete(callback)`: data is passed as params, the callback is optional
 - `execute(options)`: equivalents to `$http(options)` but the url is already set

Services objects are stored in the *services* module (unless modified in the config).

As an example, imagine we create this service on the server side:

```python
from frasco import Service, expose, current_app
class PostService(Service):
    name = 'posts'

    @expose('/posts/<id>')
    def find(self, id):
        return current_app.features.models.find_by_id('Post', id)
```

Then in an Angular controller:

```javascript
angular.module('controllers')
  .controller('PostCtrl', ['$scope', 'posts', function($scope, posts) {
    posts.find(1).get(function(post) {
        $scope.post = post;
    });
  }]);
```

## Exporting macros

Export macros as [directives](https://docs.angularjs.org/guide/directive).
In this case, the macro template can only use `{{ var_name }}`
expressions and non of the other Jinja directives.

Exporting will create a template under *static/app/partials* after the name of the
directive. A directive is then created with the *templateUrl* option.

You can control the options for the directive for each macro using a special
comment inside the macro body. This comment is of the form `{# ngdirective: json_obj #}`
where *json_obj* must be a valid json object string. The json object can also
contain a *name* key which will override the directive's name.

    {% macro post(post) %}
      {# ngdirective: {"controller": "PostCtrl"} #}
      <div class="post"><h1>{{ post.title }}</h1></div>
    {% endmacro %}

## Commands

### build

Build auto-generated files

    $ frasco angular build

### clean

Remove all auto-generated files

    $ frasco angular clean