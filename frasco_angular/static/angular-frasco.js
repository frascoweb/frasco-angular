'use strict';

var frasco = angular.module('frasco', []);

frasco.factory('frascoServiceFactory', ['$http', function($http) {
  var forEach = angular.forEach;
  return {
    makeEndpoint: function(route, args) {
      var view_args = [];
      var re = /:([a-z0-9_]+)/ig, m;
      while ((m = re.exec(route)) !== null) {
        view_args.push(m[1]);
      }

      var functionArgsToData = function(func_args) {
        var data = {};
        for (var i in args) {
          data[args[i]] = func_args[i];
        }
        return data;
      };

      var buildUrl = function(data) {
        var url = route;
        var leftover = {};
        forEach(data, function(value, key) {
          if (view_args.indexOf(key) > -1) {
            url = url.replace(":" + key, value);
          } else {
            leftover[key] = value;
          }
        })
        return {url: url, data: leftover};
      };

      var endpoint = function() {
        var spec = buildUrl(functionArgsToData(arguments));
        return {
          execute: function(options, callback) {
            options['url'] = spec.url;
            var r = $http(options);
            if (callback) r.success(callback);
            return r;
          },
          get: function(callback) {
            return this.execute({method: 'GET', params: spec.data}, callback);
          },
          post: function(callback) {
            return this.execute({method: 'POST', data: spec.data}, callback);
          },
          put: function(callback) {
            return this.execute({method: 'PUT', data: spec.data}, callback);
          },
          delete: function(callback) {
            return this.execute({method: 'DELETE', params: spec.data}, callback);
          }
        }
      };
      endpoint.url = function(data) {
        return buildUrl(data).url;
      };
      endpoint.$http = function(url_args, options) {
        options['url'] = endpoint.url(url_args);
        return $http(options);
      };
      return endpoint;
    },
    make: function(base_url, args, actions) {
      var o = {};
      var self = this;
      forEach(actions, function(spec, name) {
        o[name] = self.makeEndpoint(base_url + spec[0], args.concat(spec[1]));
      });
      return o;
    }
  };
}]);