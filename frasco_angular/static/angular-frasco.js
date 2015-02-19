'use strict';

var frasco = angular.module('frasco', []);

frasco.factory('frascoServiceFactory', ['$http', function($http) {
  var forEach = angular.forEach;
  var globalErrorHandlers = [];
  return {
    registerGlobalErrorHandler: function(callback) {
      globalErrorHandlers.push(callback);
    },
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

      var makeExecuter = function(url, data) {
        return {
          execute: function(options, successCallback, errorCallback) {
            options['url'] = url;
            var r = $http(options);
            if (successCallback) r.success(successCallback);
            var errorQ = r;
            if (errorCallback) {
              errorQ = r.catch(errorCallback);
            }
            forEach(globalErrorHandlers, function(callback) {
              errorQ = errorQ.catch(callback);
            });
            return r;
          },
          get: function(successCallback, errorCallback) {
            return this.execute({method: 'GET', params: data}, successCallback, errorCallback);
          },
          post: function(successCallback, errorCallback) {
            return this.execute({method: 'POST', data: data}, successCallback, errorCallback);
          },
          put: function(successCallback, errorCallback) {
            return this.execute({method: 'PUT', data: data}, successCallback, errorCallback);
          },
          delete: function(successCallback, errorCallback) {
            return this.execute({method: 'DELETE', params: data}, successCallback, errorCallback);
          }
        };
      };

      var endpoint = function() {
        var spec = buildUrl(functionArgsToData(arguments));
        return makeExecuter(spec.url, spec.data);
      };
      endpoint.url = function(data) {
        return buildUrl(data).url;
      };
      endpoint.$http = function(url_args, options) {
        options['url'] = endpoint.url(url_args);
        return $http(options);
      };
      endpoint.prepare = function(data) {
        var spec = buildUrl(data);
        return makeExecuter(spec.url, spec.data);
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