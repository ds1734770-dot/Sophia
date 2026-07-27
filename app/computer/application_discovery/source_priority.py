class SourcePriority:

    PRIORITIES = {

        "start_menu": 100,

        "desktop": 90,

        "registry": 80,

        "chrome_pwa": 70,

        "microsoft_store": 60,

    }

    @classmethod
    def priority(cls, application):

        return cls.PRIORITIES.get(

            application["type"],

            0,

        )