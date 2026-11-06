# Reporting-enabled native SQL reset adapter

2026-11-06. Narrow source implementation follow-on to existing SQL environment and reporting contracts. No runtime activation or training authorization.

## Test plan before implementation

| Check | Numeric acceptance |
|---|---|
| Fresh resets | 2preparedtasks x4successfulresets allocate8distinctreset channels,0crossedreports. Preparation may use1ephemeralchannel/task solely toderiveenabledprompt; those2arenotrollouts. |
| Real reporting route | One real restrictedprogram callback retains1PTCevent andexistingacknowledgment; exactly1discovered modeltool,run_program. |
| SQL/reward parity | Real observations17/29 andoriginalSQLrewards unchanged;0DBbyteschangedbyreporting. Existingfourdatasetcolumnsunchanged. |
| Quotas |9reportattemptsretain8accepted; afterexistingsubmissioncap,cap+1dispatches0additionalactions/events. |
| Reset invalidation | Clearexecution/channelbinding BEFORErowvalidation. Invalidtask/prompt/answer/db/reset failure permits0later successfulprogramcalls;diagnosticpropertyNoneuntilsuccessfulreset. |
| Disabled laziness | omitted/Nonepreserveexistingcalls/prompts/rewards;0reporting/QAimports/factorycallsin freshdisabledpath. |
| Config admission | ExactexistingReportingConfigonly, validatedbeforeDB/schema/channelwork. False/classes/subclasses/lookalikes/mutatedmalformedconfig refuse. |
| Failure retention | Reportthenprogramfailure retainsbounded diagnostics; exactprogramreturn/exceptionbehaviorunchanged,0sealed/scoredsuccessartifactscreated. |
| Immutable observations | PriorreturnedReportingSnapshotbytesneverchangeafterlaterreports/reset; no mutablesharedchannel returned. |
| Discovery | reporting_snapshot is non-callableproperty, neveranadditionaldiscoveredmodeltool. |
| Sensitivity | Forwarding-suppression control failsatintendedenabled-reportassertion,restoredcasepasses. Testsfirst;parentexecuteseligibleofflineSQLitechecks. |

## Selected lifecycle and implementation plan

PhaseA owns train/sql_bridge.py plusnew train/test_sql_bridge_reporting.py only.
Add keyword-only reporting=None to prepare_sql_training. Fornon-None validateusing existing train.sql_reporting.validate_config beforeDB/schema/channelwork; no callerchannel/factory/sink/approvalflag. Keepimportsinsideenabledpaths. Reuse existingfrozenReportingConfig, ReportingSnapshot, make_channel and snapshot_channel; do notaltertheir schemas orcollectorbehavior.
Existingrowsremain exactly prompt/task_id/answer/db_id. Enabledpromptpreparation usesfresh temporarychannel perpreparedtask anddoesnotretainchannelsormodelrollouthistory. Storetheexpectedenabledprompt andvalidatedimmutableconfig inprivatefactoryclosure. PreserveIDvalidation andsamephysicaltool/rewardDBchecks.
Eachenvironment startswith noactiveexecutor/channel. resetfirstclearsboth, thenvalidatesrowmetadata/samephysicalDB. Onlythenallocatefreshinternalchannel, calloriginal grpo_ptc.sql_environment(...,qa=channel), compareactualpromptto preparedenabledprompt, andcommitexecutor/channelonlyonsuccess. Disabled branch callsoriginalfunctionwithoutnewkwarg, notqa=None.
Addreadonly non-callable reporting_snapshot property. ReturnNonewhendisabled/unbound/afterfailedreset; otherwise derivethecurrent validated immutable ReportingSnapshot through snapshot_channel(channel,config,arm='ptc') onaccess. No snapshot sink/observercallback, globalregistry, serializedchannel, rewardchange, automaticpersistence or historylist. Liveproperty avoids wrappingexecution/failure orlosingoriginalexceptions. Keepcurrentchannel availableafterprogramfailureuntilnextreset; reportedallegationsremainunverified. run_program retainsoriginalstepreturn/exceptionsemanticsandbudgets. Propertysnapshotfailureisloudonpropertyaccess, notconvertedintosealedsuccess.

PhaseB, afterPhaseAaccepted, mayforwardtheexplicitreportingoptionthrough gatednative_training.build_sql_trainer andsql_training_run.build_monitored_sql_trainer. Defaultcallsomitthenewkwarg, originalpreflightbeforeprepare/framework/model/channelwork remains. Forwardonceonly; originaltrainer/reward/envdiscovery/callback/controlidentities;0train/save/resume. Separateworker/testsafterbridgeacceptance, no speculativeparallelwrites.

## Scope relationship and non-goals

This narrowin-processreset/factorycontract supersedes only older documents'exclusionoftheTRLresetadapter. It doesNOT upgradeexistingepisode/capture/nativeconsumerformats, isolatedtransport, productionBashroute, SDKRuntime/ScopeorCLIactivation. Sourceconstructor/reset testsarenotpatchedTRLtrainingacceptance.
No newpersistentconfig/evidenceschema, reportadjudication/authentication, callbackpersistence, exposedhostcapability, scientificmanifest/threshold/modelpolicy changes, installeddependencies, corpus/model/provider/nativeSDK/Docker/experiments/training, gateopening orspentgrantreplay. ExistinggrpoCLIrefusal andruntime/template/hardware/sourceisolation/scientificgatesstayclosed.
