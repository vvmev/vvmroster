//

var roster = angular.module('rosterApp', [
	'restangular',
	'ui.bootstrap',
	'ui.router',
]);


roster.config(function(RestangularProvider) {
	var base = window.location.pathname
	base = base.slice(-1) == '/' ? base : base + '/';
	RestangularProvider.setBaseUrl(base + 'api');
	RestangularProvider.addResponseInterceptor(function(data, operation, what, url, response, deferred) {
		data.items.extra = data.extra;
		return data.items;
	});
});
roster.config(function($stateProvider, $urlRouterProvider) {
	$urlRouterProvider.otherwise('/today');
	$stateProvider
		.state('page', {
			url: '',
			templateUrl: 'static/partials/page.html',
		})
		.state('page.today', {
			url: '/today',
			templateUrl: 'static/partials/today.html',
			controller: 'DayController',
			resolve: {
				rosterRest: function(Restangular, $filter, $rootScope) {
					$rootScope.resolving = true;
					var day = $rootScope.status.today;
					var resource = Restangular.all('roster/' + $filter('date')(day, "yyyy-MM-dd'T'"));
					return resource.getList().then(function(entries) {
						$rootScope.resolving = false;
						return {
							day: day,
							entries: entries,
							resource: resource,
						}
					});
				},
			},
		})
		.state('page.day', {
			url: '/day/{day:[^/]*}',
			templateUrl: 'static/partials/today.html',
			controller: 'DayController',
			resolve: {
				rosterRest: function(Restangular, $filter, $stateParams) {
					var day = $stateParams.day;
					var resource = Restangular.all('roster/' + $filter('date')(day, "yyyy-MM-dd'T'"));
					return resource.getList().then(function(entries) {
						return {
							day: day,
							entries: entries,
							resource: resource,
						}
					});
				},
			},
		})
		.state('page.visitors', {
			url: '/visitors',
			templateUrl: 'static/partials/visitors.html',
			controller: 'VisitorsController',
			resolve: {
				visitorRest: function(Restangular) {
					var resource = Restangular.all('visitorcount');
					return resource.getList().then(function(entries) {
						return {
							entries: entries,
							resource: resource,
						}
					});
				},
			},
		})
		.state('page.settings', {
			url: '/settings',
			templateUrl: 'static/partials/settings.html',
			controller: 'SettingsController',
			resolve: {
				settingsRest: function(Restangular) {
					var resource = Restangular.all('settings');
					return resource.getList().then(function(entries) {
						return {
							entries: entries,
							resource: resource,
						}
					});
				},
			},
		})
		.state('page.admin-users', {
			url: '/admin-users',
			templateUrl: 'static/partials/admin-users.html',
			controller: 'AdminUsersController',
			resolve: {
				adminUsersRest: function(Restangular) {
					var resource = Restangular.all('users');
					return resource.getList().then(function(entries) {
						return {
							entries: entries,
							resource: resource,
						}
					});
				},
			},
		});
});
/*
 * Override standard view switching to only allow the management views if the
 * logged in user is an admin.
 * http://stackoverflow.com/questions/22537311/angular-ui-router-login-authentication
 */
roster.run(function($state, $rootScope, $urlRouter, $log) {
	$rootScope.$log = $log;
	$rootScope.$state = $state;
	$rootScope.$on('$stateChangeStart', function(evt, toState, toStateParms) {
		if (toState.name.slice(0, 'admin'.length) == 'admin') {
			if ($rootScope.status && $rootScope.status.admin_user) {
				return;
			}
			$state.transitionTo('page.today');
		}
	});
});


/*
 * Controller for the main application view; the view shows the navigation. All actual
 * functionality is contained in the subviews.
 */
roster.controller('MainController', function(Restangular, $scope, $rootScope, $state, $timeout) {
	var resource = Restangular.all('status');
	var updateTimeout;
	var startUpdateTimer = function() {
		if (updateTimeout) {
			$timeout.cancel(updateTimeout);
		}
		updateTimeout = $timeout(update, 1*60*1000);
	}
	var update = function() {
		resource.get(1).then(function(items) {
			$scope.status = items[0];
			$rootScope.status = items[0];
			startUpdateTimer();
			$timeout(function() {
				console.log($state.current);
				if ($state.current.name == "" || $state.is('') || $state.is('page')) {
					$state.go('page.today');
				}
			}, 10);
		});
	};
	$rootScope.updateStatus = update;
	$rootScope.badgeClass = function(count) {
		if (count >= 2)
			return 'badge-success';
		if (count == 1)
			return 'badge-warning';
		return 'badge-danger';
	}
	/*
	 * On state transitions, show a spinner while the state is resolved.  The spinner
	 * is shown only after 1/4s to avoid unnecessary flickering.
	 */
	var spinnerTimer;
	var spinnerTimerStart = function() {
		if (spinnerTimer) {
			$timeout.cancel(spinnerTimer);
		}
		spinnerTimer = $timeout(function() {
			$rootScope.loading = true;
		}, 250);
	}
	$scope.$on('$stateChangeStart', function(event, toState, toParams, fromState, fromParams) {
		if (toState.resolve) {
			spinnerTimerStart();
		}
	});
	$scope.$on('$stateChangeSuccess', function(event, toState, toParams, fromState, fromParams) {
		if (toState.resolve) {
			if (spinnerTimer) {
				$timeout.cancel(spinnerTimer);
			}
			$rootScope.loading = false;
		}
	});
	update();
});


/*
 * Display and allow adding to the roster for a particular day.
 */
roster.controller('DayController', function($scope, $rootScope, $timeout, rosterRest) {
	$scope.day = rosterRest.day;
	$scope.will_sums = {
		will_open: 0,
		will_service: 0,
		will_close: 0,
	}
	var updateCounts = function() {
		$scope.will_sums.will_open = 0;
		$scope.will_sums.will_service = 0;
		$scope.will_sums.will_close = 0;
		$scope.rosterentries.map(function(e) {
			if (e.will_open)
				$scope.will_sums.will_open++;
			if (e.will_service)
				$scope.will_sums.will_service++
			if (e.will_close)
				$scope.will_sums.will_close++;
		});
		var e = $scope.myself;
		if (e.will_open)
			$scope.will_sums.will_open++;
		if (e.will_service)
			$scope.will_sums.will_service++
		if (e.will_close)
			$scope.will_sums.will_close++;
	}
	$scope.myself = {
		name: $rootScope.status.name,
		user_id: $rootScope.status.user_id,
		will_open: false,
		will_service: false,
		will_close: false,
		comment: '',
		id: undefined
	}
	var processEntries = function(entries) {
		$scope.rosterentries = [];
		entries.map(function(e) {
			if (e.user_id == $rootScope.status.user_id) {
				if ($scope.myself.id === undefined && debounceTimeout) {
					/*
					 * We're getting data from the server, but we have unsaved local
					 * changes. Copy over the fields to the server object so it can be
					 * saved.
					 */
					e.will_open =    $scope.myself.will_open;
					e.will_service = $scope.myself.will_service;
					e.will_close =   $scope.myself.will_close;
					e.comment =      $scope.myself.comment;
				}
				$scope.myself = e;
			} else {
				if (e.will_open || e.will_service || e.will_close ||
						e.comment != '') {
					$scope.rosterentries.push(e);
				}
			}
		});
		$scope.$watch('myself.will_open', debounceUpdate);
		$scope.$watch('myself.will_service', debounceUpdate);
		$scope.$watch('myself.will_close', debounceUpdate);
		$scope.$watch('myself.comment', debounceUpdate);
		updateCounts();
		startUpdateTimer();
	}
	var update = function() {
		rosterRest.resource.getList().then(processEntries);
	}
	$scope.update = update;
	$scope.save = function() {
		entry = $scope.myself;
		if (entry.id) {
			entry.put().then(function() {
				$rootScope.updateStatus();
			});
		} else {
			rosterRest.resource.post(entry).then(function() {
				update();
				$rootScope.updateStatus();
			});
		}
	}
	var updateTimeout;
	var startUpdateTimer = function() {
		if (updateTimeout) {
			$timeout.cancel(updateTimeout);
		}
		updateTimeout = $timeout(update, 5*60*1000);
	};
	var debounceTimeout;
	var debounceUpdate = function(newVal, oldVal, scope) {
		if (newVal === oldVal) {
			return;
		}
		updateCounts();
		if (debounceTimeout) {
			$timeout.cancel(debounceTimeout);
		}
		if (!$scope.myself.id) {
			// if we don't have an entry yet, create it asap
			$scope.save();
		}
		debounceTimeout = $timeout($scope.save, 1000);
		startUpdateTimer();
	};
	processEntries(rosterRest.entries);
});


/*
 * Display visitor counts.
 */
roster.controller('VisitorsController', function($scope, $rootScope, $timeout, visitorRest) {
	$scope.entries = []
	$scope.extra = visitorRest.entries.extra;
	visitorRest.entries.map(function(e) {
		// convert timestamp to JS date so we can use the prototype functions in the
		// template
		e.ts = new Date(e.ts);
		$scope.entries.push(e);
	});
});


/*
 * Allow users to change their password and certain other settings.
 */
roster.controller('SettingsController', function($scope, $modal, settingsRest) {
	$scope.user = settingsRest.entries[0];
	$scope.update = function() {
		settingsRest.resource.getList().then(function(entries) {
			$scope.user = entries[0];
		});
	}
	$scope.save = function() {
		$scope.user.put().then(function(){
			$rootScope.updateStatus();
		});
	}
	$scope.changePassword = function() {
		var passwords = {
			old: '',
			new1: '',
			new2: '',
		};
		var modalInstance = undefined;
		var modalOpen = function(alert) {
			modalInstance = $modal.open({
				templateUrl: 'changePassword.html',
				controller: function($scope, passwords, alert) {
					$scope.ok = modalInstance.close;
					$scope.cancel = modalInstance.dismiss;
					$scope.passwords = passwords;
					$scope.alert = alert;
				},
				backdrop: 'static',
				resolve: {
					passwords: function() { return passwords; },
					alert: function() { return alert; },
				}
			});
		}
		var modalThen = function() {
			if (passwords.new1 != passwords.new2) {
				modalOpen('Die beiden neuen Passwörter müssen übereinstimmen.');
			}
			settingsRest.resource.post(passwords).then(function() {
			}, function(response) {
				modalOpen(response.data.msg);
				modalInstance.result.then(modalThen);
			});
		}
		modalOpen('');
		modalInstance.result.then(modalThen);
	}
});


/*
 * Admins can create, update, and delete users.
 */
roster.controller('AdminUsersController', function($scope, $modal, adminUsersRest) {
	$scope.userentries = adminUsersRest.entries;
	var update = function() {
		adminUsersRest.resource.getList().then(function(entries) {
			$scope.userentries = entries;
		});
	}
	var useredit = function(user, action) {
		var modalInstance = $modal.open({
			templateUrl: 'useredit.html',
			controller: function($scope, $modalInstance) {
				$scope.user = user;
				$scope.alert = "";
				$scope.buttonsDisabled = false;
				$scope.ok = function() {
					$scope.buttonsDisabled = true;
					action().then(function() {
						$modalInstance.close();
					}, function(response) {
						$scope.alert = response.data.msg;
						$scope.buttonsDisabled = false;
					});
				};
				$scope.cancel = function() {
					$modalInstance.dismiss('cancel');
				};
			},
		});
		modalInstance.result.then(function() {
			update();
		});
	};
	$scope.useradd = function() {
		var user = {
			'id': undefined,
			'name': '',
			'email': '',
			'password': '',
			'admin_user': false,
		};
		useredit(user, function() {
			return adminUsersRest.resource.post(user);
		});
	};
	$scope.useredit = function(aUser) {
		var user = aUser.clone();
		useredit(user, function() {
			return user.put();
		});
	};
	$scope.userdelete = function(user) {
		var modalInstance = $modal.open({
			templateUrl: 'userdelete.html',
			controller: function($scope, $modalInstance) {
				$scope.user = user;
				$scope.alert = "";
				$scope.buttonsDisabled = false;
				$scope.ok = function() {
					$scope.buttonsDisabled = true;
					user.remove().then(function() {
						$modalInstance.close();
					}, function(response) {
						$scope.alert = response.data.msg;
						$scope.buttonsDisabled = false;
					});
				};
				$scope.cancel = function() {
					$modalInstance.dismiss('cancel');
				};
			},
		});
		modalInstance.result.then(function() {
			update();
		});
	};
	update();
});
