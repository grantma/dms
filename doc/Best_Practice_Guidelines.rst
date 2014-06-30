.. _best-practice-guidelines:

************************
Best Practice Guidelines
************************

Anycast Redux
=============

Refer to RFCs 3528 and 4786. Also refer to `http://dns.isc.org/f-root/` and `http://www.isc.org/solutions/sns-anycast`

* ISCs experience is that a combination of anycast and unicast DNS servers is
  the most reliable. Due to routing and load balancing instabilities, the
  unicast servers are required to fill in the holes of service.  Like
  interference fringes from overlapping point wave sources.

* Small length TCP sessions mostly work.

* Keep Local node routing to one AS as mush as possible, due to trouble
  shooting difficulties.

* Global node routing has to be very stable.

* As soon as a DNS server can't keep content in sync with master, just shut
  down named, rather than withdrawing route.

* Turn off PMTU on anycast DNS servers

* Don't filter UDP fragments

* Set IPv6 MTU on anycast servers to 1280 bytes to avoid fragmentation.

Remember that DNS resolvers are v. good at handling non-responsive servers.

Also note that anycast address should at least be on a loopback interface.

Good idea for anycast/slave server to have 2 interfaces - one for query
traffic, the other for admin and talking to master server. These should be
connected to separate interfaces on upstream router. Avoids a DOS overflowing
TX queue affecting admin of the server


